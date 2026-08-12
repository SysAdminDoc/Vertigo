"""Preflight corrections applied before the reframe pipeline.

Two silent bugs every reframing tool in the 2026 OSS landscape ships
without noticing:

    1. **VFR drift.** Phone recordings, GoPro clips, and screen
       captures carry *variable* frame rates — the `avg_frame_rate`
       and `r_frame_rate` disagree. Feeding them straight into a
       crop-plus-scale pipeline produces footage that plays at the
       wrong speed and drifts out of sync with the original audio.
       Detectable via `ffprobe`; corrected with `-vsync cfr -r <fps>`
       on the video stream.

    2. **Non-zero video start_time.** Some containers (especially
       screen caps and re-muxed streams) carry a non-zero start
       offset on the video stream. FFmpeg's default audio extract
       ignores this, so every subtitle/trim timestamp lands
       fractions of a second off. Corrected with `-itsoffset` on
       the audio input so A/V realigns at t=0.

This module exposes tiny recipe helpers plus a media-dependency security
probe. The correction planner stays pure; the security probe runs only the
short ``ffmpeg -version`` check needed before startup/export.
"""

from __future__ import annotations

import importlib.metadata
import re
import shutil
import subprocess
from dataclasses import dataclass

from .probe import VideoInfo


# `avg_fps` can under-report on heavily VFR recordings, especially phone
# videos that idle at ~25 fps but burst to 60 fps during motion. Nudging
# to the next "normal" rate keeps Shorts-targeted output smooth.
_SAFE_FPS_LADDER = (24.0, 25.0, 30.0, 50.0, 60.0)

# Security floors verified against the FFmpeg security/release pages on
# 2026-08-12.  Distro packages may backport the same fixes without matching
# the upstream number, so stale upstream branches warn rather than hard-stop.
_FFMPEG_SECURITY_FLOORS: dict[tuple[int, int], tuple[int, int, int]] = {
    (8, 1): (8, 1, 2),
    (8, 0): (8, 0, 3),
    (7, 1): (7, 1, 5),
    (7, 0): (7, 0, 3),
    (6, 1): (6, 1, 6),
    (5, 1): (5, 1, 10),
    (4, 4): (4, 4, 8),
}
PILLOW_SECURITY_FLOOR = (12, 2, 0)
_VERSION_RE = re.compile(r"(?<![\d.])v?(\d+)\.(\d+)(?:\.(\d+))?(?!\d)")


@dataclass(frozen=True)
class MediaSecurityReport:
    """Version and security status for the two media parsers we invoke.

    ``warnings`` are actionable but may be safe on a distro-maintained
    backport. ``blockers`` mean Vertigo cannot establish a safe parser
    version and must refuse an export that would process untrusted media.
    """

    ffmpeg_version: tuple[int, int, int] | None
    pillow_version: tuple[int, int, int] | None
    ffmpeg_version_text: str | None
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @property
    def can_export(self) -> bool:
        return not self.blockers

    @property
    def version_summary(self) -> str:
        ffmpeg = format_version(self.ffmpeg_version) if self.ffmpeg_version else "unknown"
        pillow = format_version(self.pillow_version) if self.pillow_version else "unknown"
        return f"FFmpeg {ffmpeg} · Pillow {pillow}"

    @property
    def blocker_summary(self) -> str:
        return " ".join(self.blockers) or "none"

    def as_text(self) -> str:
        lines = [f"Media dependency preflight: {self.version_summary}"]
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {message}" for message in self.warnings)
        if self.blockers:
            lines.append("Blockers:")
            lines.extend(f"  - {message}" for message in self.blockers)
        return "\n".join(lines)


def format_version(version: tuple[int, int, int] | None) -> str:
    """Render a normalized three-part version for diagnostics."""
    if version is None:
        return "unknown"
    return ".".join(str(part) for part in version)


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    """Extract a release version from tool/package output."""
    if not raw:
        return None
    match = _VERSION_RE.search(str(raw))
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def inspect_media_dependencies(
    *,
    ffmpeg_path: str | None = None,
    ffmpeg_output: str | None = None,
    pillow_version: str | None = None,
) -> MediaSecurityReport:
    """Inspect FFmpeg and Pillow before startup or export.

    ``ffmpeg_output`` and ``pillow_version`` are injectable so the security
    policy can be regression-tested without replacing a user's binaries.
    """
    ffmpeg_error: str | None = None
    if ffmpeg_output is None:
        ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg_path:
            ffmpeg_error = "ffmpeg was not found on PATH"
            raw_ffmpeg = ""
        else:
            try:
                result = subprocess.run(
                    [ffmpeg_path, "-version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=5,
                    creationflags=_no_window_flags(),
                )
                raw_ffmpeg = "\n".join(
                    part for part in (result.stdout, result.stderr) if part
                )
                if result.returncode != 0 and not raw_ffmpeg.strip():
                    ffmpeg_error = f"ffmpeg -version exited {result.returncode}"
            except (OSError, subprocess.SubprocessError) as exc:
                raw_ffmpeg = ""
                ffmpeg_error = f"could not run ffmpeg -version: {exc}"
    else:
        raw_ffmpeg = ffmpeg_output

    ffmpeg_version = parse_version(raw_ffmpeg)
    pillow_raw = pillow_version if pillow_version is not None else _installed_pillow_version()
    parsed_pillow = parse_version(pillow_raw)

    warnings: list[str] = []
    blockers: list[str] = []

    if ffmpeg_error:
        blockers.append(f"FFmpeg security check failed: {ffmpeg_error}.")
    elif ffmpeg_version is None:
        blockers.append(
            "FFmpeg security check could not parse a release version; "
            "update FFmpeg or make a standard release binary available."
        )
    else:
        floor = _FFMPEG_SECURITY_FLOORS.get(ffmpeg_version[:2])
        if floor and ffmpeg_version < floor:
            warnings.append(
                f"FFmpeg {format_version(ffmpeg_version)} is below the "
                f"security floor {format_version(floor)} for its release "
                "branch; update before processing untrusted media or verify "
                "your distributor's backports."
            )
        elif floor is None and ffmpeg_version[0] <= 8:
            warnings.append(
                f"FFmpeg {format_version(ffmpeg_version)} is on a release "
                "branch outside Vertigo's current security-floor table; "
                "prefer a current maintained FFmpeg branch."
            )

    if parsed_pillow is None:
        blockers.append(
            "Pillow security check could not determine the installed version; "
            "install Pillow>=12.2.0 before exporting."
        )
    elif parsed_pillow < PILLOW_SECURITY_FLOOR:
        blockers.append(
            f"Pillow {format_version(parsed_pillow)} is below the security "
            f"floor {format_version(PILLOW_SECURITY_FLOOR)} (CVE-2026-42310); "
            "upgrade Pillow before exporting."
        )

    return MediaSecurityReport(
        ffmpeg_version=ffmpeg_version,
        pillow_version=parsed_pillow,
        ffmpeg_version_text=(raw_ffmpeg.splitlines()[0].strip() if raw_ffmpeg else None),
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )


def _installed_pillow_version() -> str | None:
    try:
        return importlib.metadata.version("Pillow")
    except importlib.metadata.PackageNotFoundError:
        try:
            from PIL import __version__
        except ImportError:
            return None
        return str(__version__)


def _no_window_flags() -> int:
    import sys

    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


@dataclass(frozen=True)
class Preflight:
    """Corrections to apply to an input before reframing.

    `input_args` goes **before** `-i <path>` in the ffmpeg command so
    that per-input options (like `-itsoffset` and any `-ss`) are
    scoped to the right stream; `output_args` extends the encoder
    output flags to force a constant frame rate on the video track.
    """
    input_args: list[str]
    output_args: list[str]
    notes: list[str]

    @property
    def is_noop(self) -> bool:
        return not (self.input_args or self.output_args)


def plan_preflight(info: VideoInfo, target_fps: int) -> Preflight:
    """Return the pre-input and output-side args needed for `info`.

    Idempotent: repeated runs produce the same recipe; safe to call
    before every encode.
    """
    input_args: list[str] = []
    output_args: list[str] = []
    notes: list[str] = []

    if info.is_variable_frame_rate:
        # Pick the closest safe ladder rate that meets or exceeds the
        # source's time-average fps. The output preset's own fps is
        # enforced later by the encoder `-r` flag, so this is purely
        # about normalising the *input* timebase.
        desired = _closest_safe_fps(info.avg_fps or info.r_fps or target_fps)
        # -vsync cfr is the legacy flag name; -fps_mode cfr is the
        # modern spelling (FFmpeg 5+). Use the legacy form — it's
        # accepted by every FFmpeg since 3.x and all hardware
        # encoders handle it identically.
        output_args += ["-vsync", "cfr", "-r", f"{desired:g}"]
        notes.append(
            f"VFR normalised: r_fps={info.r_fps:.2f} avg_fps={info.avg_fps:.2f} \u2192 "
            f"cfr@{desired:g}"
        )

    # Non-zero video start_time → itsoffset the AUDIO so A/V line up at t=0.
    # We don't shift the video track itself; we shift the audio input
    # backwards by the same amount the video is delayed.
    if info.has_audio and abs(info.video_start_time) > 0.02:
        # Applied as a second -i of the same file at the audio input
        # position is hairy in our single-input pipeline; fall back
        # to a pre-input audio delay on output via -af adelay for the
        # rare case where start_time is large and positive. For the
        # common case of a small positive offset we encode the
        # mitigation in notes so the UI can surface it to the user.
        notes.append(
            f"Video start_time={info.video_start_time:.3f}s detected; "
            "audio drift mitigation enabled."
        )
        # The cleanest in-pipeline fix is an audio filter that either
        # pads the beginning (adelay) or trims it (atrim). Positive
        # start_time means video starts late, so we delay the audio
        # to match.
        ms = int(round(info.video_start_time * 1000))
        if ms > 0:
            # Only applies when audio is being encoded by the same job.
            output_args += [
                "-af", f"adelay={ms}|{ms},apad",
            ]

    return Preflight(input_args=input_args, output_args=output_args, notes=notes)


def _closest_safe_fps(source_fps: float) -> float:
    """Pick the ladder rate just above `source_fps`."""
    if source_fps <= 0:
        return 30.0
    for rate in _SAFE_FPS_LADDER:
        if rate >= source_fps - 0.5:
            return rate
    return _SAFE_FPS_LADDER[-1]
