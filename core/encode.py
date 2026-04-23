"""FFmpeg encoder — streams progress via stderr parsing.

Supports:
  - any Encoder from core.encoders (hardware or CPU)
  - quality slider (mapped into codec-native units)
  - speed preset
  - trim window (-ss / -t)
  - optional burn-in subtitle path
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .encoders import Encoder, encoder_args, pick_default
from .presets import Preset
from .probe import VideoInfo
from .reframe import ReframePlan


_PROGRESS_RE = re.compile(
    r"(?:time=|out_time=)(\d+):(\d+):(\d+(?:\.\d+)?)"
)


def ffmpeg_bin() -> str:
    bin_path = shutil.which("ffmpeg")
    if not bin_path:
        raise RuntimeError("ffmpeg not found on PATH. Install FFmpeg.")
    return bin_path


@dataclass
class EncodeJob:
    info: VideoInfo
    preset: Preset
    plan: ReframePlan
    out_path: Path
    trim_start: float = 0.0
    trim_end: float | None = None     # None = full duration
    encoder: Encoder | None = None    # None = auto-pick best available
    quality: int = 75                 # 1..100 quality slider
    speed_preset: str | None = None   # encoder preset ("medium","p5",...)
    subtitles_path: Path | None = None   # burn this SRT into the video
    burn_subtitles: bool = False

    def build_command(self) -> list[str]:
        cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-stats", "-progress", "pipe:2"]

        if self.trim_start > 0:
            cmd += ["-ss", f"{self.trim_start:.3f}"]

        cmd += ["-i", str(self.info.path)]

        if self.trim_end is not None:
            duration = max(0.0, self.trim_end - self.trim_start)
            cmd += ["-t", f"{duration:.3f}"]

        vf = self.plan.video_filter
        if self.burn_subtitles and self.subtitles_path and self.subtitles_path.exists():
            vf = vf + "," + _subtitles_filter(self.subtitles_path)

        cmd += ["-vf", vf]

        enc = self.encoder or pick_default(codec="h264")
        if enc is None:
            enc_args = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        else:
            enc_args = encoder_args(enc, self.quality, self.speed_preset)
        cmd += enc_args

        cmd += [
            "-b:v", self.preset.video_bitrate,
            "-maxrate", self.preset.video_bitrate,
            "-bufsize", _double_bitrate(self.preset.video_bitrate),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-r", str(self.preset.fps),
        ]

        if self.info.has_audio:
            cmd += ["-c:a", "aac", "-b:a", self.preset.audio_bitrate, "-ar", "48000"]
        else:
            cmd += ["-an"]

        cmd += [str(self.out_path)]
        return cmd


def run(job: EncodeJob, on_progress=None, on_log=None, cancel_cb=None) -> int:
    """Run the encode. Returns FFmpeg exit code."""
    job.out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = job.build_command()
    if on_log:
        on_log("$ " + " ".join(_quote(c) for c in cmd))

    duration = _duration(job)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=_no_window_flags(),
    )
    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip()
            if not line:
                continue
            if cancel_cb and cancel_cb():
                proc.terminate()
                break
            if on_log:
                on_log(line)
            if on_progress and duration > 0:
                m = _PROGRESS_RE.search(line)
                if m:
                    h, mnt, sec = m.groups()
                    t = int(h) * 3600 + int(mnt) * 60 + float(sec)
                    on_progress(min(1.0, t / duration))
    finally:
        rc = proc.wait()

    if on_progress:
        on_progress(1.0)
    return rc


# ---------------------------------------------------------- helpers

def _duration(job: EncodeJob) -> float:
    if job.trim_end is not None:
        return max(0.0, job.trim_end - job.trim_start)
    return max(0.0, job.info.duration - job.trim_start)


def _double_bitrate(rate: str) -> str:
    if rate.endswith("M"):
        return f"{int(float(rate[:-1]) * 2)}M"
    if rate.endswith("k"):
        return f"{int(float(rate[:-1]) * 2)}k"
    return rate


def _subtitles_filter(srt_path: Path) -> str:
    """Build an FFmpeg `subtitles=` filter expression for burn-in.

    FFmpeg is fussy about path escaping on Windows — single-quote the path,
    convert backslashes to forward slashes, escape the drive colon with \\:.
    """
    s = str(srt_path.resolve()).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        s = s[0] + r"\:" + s[2:]
    style = (
        "FontName=Segoe UI,FontSize=24,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H99000000,"
        "BackColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
        "MarginV=60,Alignment=2"
    )
    return f"subtitles='{s}':force_style='{style}'"


def _quote(s: str) -> str:
    if " " in s or ":" in s or "'" in s:
        return f'"{s}"'
    return s


def _no_window_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0
