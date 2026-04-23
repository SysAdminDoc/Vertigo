"""ffprobe wrapper — extracts metadata from any video container.

Captures the extra facts needed by the preflight pipeline (see
`core.preflight`):

    * `r_frame_rate` + `avg_frame_rate` — inequality signals VFR
    * `start_time` on the video stream — non-zero offsets produce
      audio drift unless compensated during audio extract.

These are derived, not raw ratios, so the rest of the code can stay
simple.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    width: int
    height: int
    duration: float
    fps: float                  # effective fps (avg_frame_rate preferred)
    codec: str
    has_audio: bool
    audio_codec: str | None
    # Facts needed by the preflight pipeline:
    r_fps: float = 0.0          # container-reported real frame rate
    avg_fps: float = 0.0        # time-based average frame rate
    video_start_time: float = 0.0  # seconds offset of video stream

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def is_landscape(self) -> bool:
        return self.aspect > 1.05

    @property
    def is_vertical(self) -> bool:
        return self.aspect < 0.95

    @property
    def is_variable_frame_rate(self) -> bool:
        """True when avg_fps and r_fps meaningfully diverge (> 1% delta).

        The 1% floor guards against float-rounding noise; in practice
        VFR recordings (phone-shot MP4, GoPro with timecode, screen
        captures) show 5–30% deltas between r and avg frame rates.
        """
        if self.r_fps <= 0 or self.avg_fps <= 0:
            return False
        delta = abs(self.r_fps - self.avg_fps) / max(self.r_fps, self.avg_fps)
        return delta > 0.01


def _ffprobe_bin() -> str:
    bin_path = shutil.which("ffprobe")
    if not bin_path:
        raise RuntimeError("ffprobe not found on PATH. Install FFmpeg.")
    return bin_path


def probe(path: str | Path) -> VideoInfo:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    cmd = [
        _ffprobe_bin(),
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        creationflags=_no_window_flags(),
    )
    data = json.loads(result.stdout)

    video_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if not video_stream:
        raise ValueError(f"No video stream in {path}")

    width = int(video_stream["width"])
    height = int(video_stream["height"])
    codec = video_stream["codec_name"]

    r_fps = _parse_fps(video_stream.get("r_frame_rate", "0/1"))
    avg_fps = _parse_fps(video_stream.get("avg_frame_rate", "0/1"))
    fps = avg_fps or r_fps or 30.0

    duration = float(data["format"].get("duration") or video_stream.get("duration") or 0.0)

    start_time = 0.0
    try:
        start_time = float(video_stream.get("start_time") or data["format"].get("start_time") or 0.0)
    except (TypeError, ValueError):
        start_time = 0.0

    return VideoInfo(
        path=path,
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        codec=codec,
        has_audio=audio_stream is not None,
        audio_codec=audio_stream["codec_name"] if audio_stream else None,
        r_fps=r_fps,
        avg_fps=avg_fps,
        video_start_time=start_time,
    )


def _parse_fps(raw: str) -> float:
    if "/" in raw:
        num, den = raw.split("/", 1)
        try:
            n, d = float(num), float(den)
            return n / d if d else 0.0
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _no_window_flags() -> int:
    import sys
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0
