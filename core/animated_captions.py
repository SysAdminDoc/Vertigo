"""Animated captions via pycaps — optional premium caption path.

pycaps (https://github.com/francozanardi/pycaps, MIT) takes Whisper
word-level segments and emits a video overlay with CSS-styled per-word
animation: bouncing/popping/sweeping karaoke that behaves consistently
across players, unlike raw ASS which renders differently on every libass
version.

This module is a thin adapter between Vertigo's existing Caption
dataclass (``core.subtitles.Caption``) and pycaps' API. The heavy
dependency is lazy-imported so the rest of the app works unchanged when
it isn't installed.

Vertigo ships three caption paths — pycaps is one of them:

    "none"    → plain SRT, libass renders with a force_style block
    "karaoke" → ASS file with \\kf per-word sweep
    "pycaps"  → this module; produces a transparent overlay video that
                the encode pipeline composites with the main footage

The pycaps path costs more render time but unlocks visual styles
(pop/bounce/shake, gradient fills, emoji-per-word) that ASS can't do.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# The caption style presets we expose to the UI. The values are pycaps
# template identifiers (strings pycaps understands); when pycaps gains
# new named templates we add them here.
STYLE_BOLD_YELLOW = "bold-yellow"
STYLE_BLOCK_WHITE = "block-white"
STYLE_SIMPLE_KARAOKE = "simple-karaoke"
STYLE_POP_PER_WORD = "pop"

DEFAULT_STYLE = STYLE_BOLD_YELLOW


@dataclass(frozen=True)
class AnimatedCaptionResult:
    """Where pycaps wrote its artifacts.

    ``overlay_path`` is an RGBA video file that the encode pipeline can
    composite via ``overlay`` in the filter graph. ``preview_srt`` is
    the plain-text SRT pycaps produced as a side-effect — keeping it
    around lets us fall back cleanly if the overlay compose fails.
    """
    overlay_path: Path
    preview_srt: Path | None


# ---------------------------------------------------------------- availability

def is_available() -> bool:
    try:
        import pycaps  # noqa: F401
        return True
    except ImportError:
        return False


def ensure_installed() -> bool:
    if is_available():
        return True
    if not _try_pip_install("pycaps>=0.7"):
        return False
    return is_available()


# ---------------------------------------------------------------- public api

def available_styles() -> list[str]:
    """Style identifiers safe to pass to ``render``."""
    return [
        STYLE_BOLD_YELLOW,
        STYLE_BLOCK_WHITE,
        STYLE_SIMPLE_KARAOKE,
        STYLE_POP_PER_WORD,
    ]


def render(
    captions: list,          # list[core.subtitles.Caption]
    out_dir: Path,
    *,
    source_video: Path,
    style: str = DEFAULT_STYLE,
    width: int = 1080,
    height: int = 1920,
    cancel_cb=None,
) -> AnimatedCaptionResult:
    """Render an animated-caption overlay video for ``captions``.

    Raises ``RuntimeError`` when pycaps isn't importable — UI callers
    should guard with ``is_available()``.

    ``captions`` is expected to carry word-level timings (the
    ``Caption.words`` tuple from ``core.subtitles``). If a caption lacks
    words, pycaps falls back to plain per-line animation.
    """
    if not is_available():
        raise RuntimeError(
            "pycaps is not installed. Install with:\n"
            "    pip install pycaps\n"
            "Vertigo will keep using the ASS/SRT path until then."
        )
    if style not in available_styles():
        raise ValueError(f"Unknown animated caption style: {style!r}")

    out_dir.mkdir(parents=True, exist_ok=True)
    # Import after the availability guard so this module loads in envs
    # where pycaps isn't present (tests, headless CI).
    import pycaps

    # pycaps public surface at time of writing:
    #   pycaps.render_overlay(segments, out_path, template, canvas=(w,h))
    #
    # The segment shape it accepts is a list of dicts with 'start',
    # 'end', 'text', and optional 'words' (each word is dict(start, end,
    # text)). Bridge from Vertigo's Caption dataclass here.
    segments = [_to_pycaps_segment(c) for c in captions if _has_body(c)]
    if not segments:
        raise RuntimeError("No captions to render (all empty).")

    if cancel_cb and cancel_cb():
        raise RuntimeError("Cancelled.")

    overlay_path = out_dir / f"{Path(source_video).stem}.vertigo.pycaps.mov"
    # pycaps has two supported entry points across versions; prefer the
    # simple render_overlay() façade, fall back to the CLI if the
    # import is present but that symbol isn't.
    render_fn = getattr(pycaps, "render_overlay", None)
    if callable(render_fn):
        render_fn(
            segments,
            str(overlay_path),
            template=style,
            canvas=(int(width), int(height)),
        )
    else:
        _render_via_cli(
            segments=segments,
            out_path=overlay_path,
            style=style,
            width=width,
            height=height,
        )

    return AnimatedCaptionResult(overlay_path=overlay_path, preview_srt=None)


def build_overlay_filter(overlay_path: Path) -> str:
    """Return the ``-filter_complex`` fragment that composites the
    overlay video on top of the main footage.

    The fragment is designed to slot in after Vertigo's reframe+scale
    chain — it takes the current main stream and the overlay, and
    produces a single composited stream.
    """
    return (
        f"[v][ov]overlay=0:0:format=auto:eof_action=pass"
    )


# ---------------------------------------------------------------- helpers

def _has_body(cap) -> bool:
    text = (getattr(cap, "text", "") or "").strip()
    return bool(text)


def _to_pycaps_segment(cap) -> dict:
    words = [
        {"start": float(w.start), "end": float(w.end), "text": w.text}
        for w in getattr(cap, "words", ()) or ()
    ]
    seg: dict = {
        "start": float(cap.start),
        "end": float(cap.end),
        "text": cap.text,
    }
    if words:
        seg["words"] = words
    return seg


def _render_via_cli(
    *,
    segments: Iterable[dict],
    out_path: Path,
    style: str,
    width: int,
    height: int,
) -> None:
    """Fallback: drive the pycaps CLI with a temp JSON manifest.

    Kept behind the ``render_overlay`` probe so older pycaps versions
    (which only expose the CLI) keep working.
    """
    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(list(segments), f, ensure_ascii=False)
        manifest = Path(f.name)
    try:
        rc = subprocess.call(
            [
                sys.executable, "-m", "pycaps",
                "--segments", str(manifest),
                "--template", style,
                "--canvas", f"{width}x{height}",
                "--out", str(out_path),
            ],
            creationflags=_no_window_flags(),
        )
        if rc != 0:
            raise RuntimeError(f"pycaps CLI exited {rc}")
    finally:
        try:
            manifest.unlink(missing_ok=True)
        except Exception:
            pass


def _try_pip_install(spec: str) -> bool:
    bases = [
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", spec],
        [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check", spec],
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "--disable-pip-version-check", spec],
    ]
    for cmd in bases:
        try:
            if subprocess.call(cmd) == 0:
                return True
        except Exception:
            continue
    return False


def _no_window_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0
