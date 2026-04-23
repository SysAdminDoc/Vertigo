"""Subtitle generation via faster-whisper.

`faster-whisper` is a heavy dependency (~200 MB incl. CTranslate2 runtime),
so we keep it **opt-in**: it is not in the bootstrap list; the first call to
`transcribe_to_srt()` will attempt to pip-install it on demand. The UI
surfaces this as an explicit "Enable AI captions" action.

Output is a standard SRT file written next to the source clip (or wherever
`out_path` points). `EncodeJob.subtitles_path` can then consume it.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "small"
AVAILABLE_MODELS = ("tiny", "base", "small", "medium", "large-v3")


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


def ensure_installed() -> bool:
    """Return True if faster-whisper is importable. Attempts lazy install."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        pass
    if not _try_pip_install("faster-whisper>=1.0.3"):
        return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def is_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(
    source: Path,
    *,
    model_name: str = DEFAULT_MODEL,
    language: str | None = None,
    progress_cb=None,
    cancel_cb=None,
) -> list[Caption]:
    """Run faster-whisper on `source` audio. Returns caption segments."""
    if not ensure_installed():
        raise RuntimeError("faster-whisper is not installed and could not be auto-installed.")

    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="auto", compute_type="auto")

    segments_iter, info = model.transcribe(
        str(source),
        language=language,
        vad_filter=True,
        word_timestamps=False,
    )
    total = max(1e-6, float(info.duration or 0.0))

    out: list[Caption] = []
    for seg in segments_iter:
        if cancel_cb and cancel_cb():
            break
        out.append(Caption(start=float(seg.start or 0.0), end=float(seg.end or 0.0), text=(seg.text or "").strip()))
        if progress_cb:
            progress_cb(min(1.0, (seg.end or 0.0) / total))
    if progress_cb:
        progress_cb(1.0)
    return out


def write_srt(captions: list[Caption], out_path: Path) -> Path:
    lines: list[str] = []
    for i, c in enumerate(captions, start=1):
        if not c.text:
            continue
        lines.append(str(i))
        lines.append(f"{_fmt(c.start)} --> {_fmt(c.end)}")
        lines.append(_wrap(c.text))
        lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def transcribe_to_srt(
    source: Path,
    out_path: Path,
    *,
    model_name: str = DEFAULT_MODEL,
    language: str | None = None,
    progress_cb=None,
    cancel_cb=None,
) -> Path:
    captions = transcribe(
        source,
        model_name=model_name,
        language=language,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
    )
    return write_srt(captions, out_path)


# ---------------------------------------------------------- helpers

def _fmt(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _wrap(text: str, max_per_line: int = 36) -> str:
    """Soft-wrap long captions at word boundaries for legibility on mobile."""
    text = " ".join(text.split())
    if len(text) <= max_per_line:
        return text
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for w in words:
        if not current:
            current = w
        elif len(current) + 1 + len(w) <= max_per_line:
            current += " " + w
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return "\n".join(lines[:2])  # max 2 lines per caption, mobile-safe


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
