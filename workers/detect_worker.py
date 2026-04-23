"""QThread — runs FaceTracker off the UI thread.

When `crop_width_frac` is provided, uses the cameraman-driven pipeline
(`SpeakerTracker` + `SmoothedCameraman`) for multi-face, speaker-sticky
viewport motion. Without it, falls back to the legacy single-largest-
face-per-frame path so callers with no clip geometry still get a track.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.detect import FaceTracker


class DetectWorker(QThread):
    progress = pyqtSignal(float)      # 0..1
    finished_ok = pyqtSignal(list)    # list[TrackPoint]
    failed = pyqtSignal(str)

    def __init__(
        self,
        video_path: Path,
        sample_fps: float = 2.0,
        smoothing: float = 0.6,
        *,
        crop_width_frac: float | None = None,
    ) -> None:
        super().__init__()
        self._path = Path(video_path)
        self._sample_fps = sample_fps
        self._smoothing = smoothing
        self._crop_width_frac = crop_width_frac
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        tracker = FaceTracker(sample_fps=self._sample_fps, smoothing=self._smoothing)
        try:
            if self._crop_width_frac is not None and 0 < self._crop_width_frac <= 1.0:
                points = tracker.track_with_cameraman(
                    self._path,
                    crop_width_frac=self._crop_width_frac,
                    progress_cb=self.progress.emit,
                    cancel_cb=lambda: self._cancel,
                )
            else:
                points = tracker.track(
                    self._path,
                    progress_cb=self.progress.emit,
                    cancel_cb=lambda: self._cancel,
                )
            self.finished_ok.emit(points)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            tracker.close()
