"""QThread that runs faster-whisper off the UI thread.

Output format is selected by the active caption preset: karaoke presets
with per-word animation write an ASS file; all other presets write SRT.
libass is happy with either, so the FFmpeg burn-in path is identical.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.caption_styles import CaptionPreset, default_preset
from core.subtitles import DEFAULT_MODEL, transcribe_to_file


class SubtitleWorker(QThread):
    progress = pyqtSignal(float)           # 0..1
    status = pyqtSignal(str)               # log line
    finished_ok = pyqtSignal(str)          # final subtitle file path
    failed = pyqtSignal(str)

    def __init__(
        self,
        source: Path,
        out_dir: Path,
        *,
        preset: CaptionPreset | None = None,
        height_px: int = 1920,
        model_name: str = DEFAULT_MODEL,
        language: str | None = None,
        face_aware: bool = False,
        letterbox: bool = False,
    ) -> None:
        super().__init__()
        self._source = Path(source)
        self._out_dir = Path(out_dir)
        self._preset = preset or default_preset()
        self._height = height_px
        self._model = model_name
        self._language = language
        self._face_aware = face_aware
        self._letterbox = letterbox
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            face_note = "  \u00b7  face-aware layout" if self._face_aware and not self._letterbox else ""
            self.status.emit(
                f"Loading faster-whisper ({self._model}) \u2014 {self._preset.label} preset{face_note}"
            )
            if self._face_aware and not self._letterbox:
                self.status.emit("Sampling faces for caption placement\u2026")
            path = transcribe_to_file(
                self._source,
                self._out_dir,
                preset=self._preset,
                height_px=self._height,
                model_name=self._model,
                language=self._language,
                face_aware=self._face_aware,
                letterbox=self._letterbox,
                progress_cb=self.progress.emit,
                cancel_cb=lambda: self._cancel,
            )
            if self._cancel:
                self.failed.emit("Cancelled.")
                return
            self.finished_ok.emit(str(path))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
