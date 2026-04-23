"""QThread that runs faster-whisper off the UI thread."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.subtitles import DEFAULT_MODEL, transcribe_to_srt


class SubtitleWorker(QThread):
    progress = pyqtSignal(float)           # 0..1
    status = pyqtSignal(str)               # log line
    finished_ok = pyqtSignal(str)          # SRT path
    failed = pyqtSignal(str)

    def __init__(
        self,
        source: Path,
        out_path: Path,
        *,
        model_name: str = DEFAULT_MODEL,
        language: str | None = None,
    ) -> None:
        super().__init__()
        self._source = Path(source)
        self._out_path = Path(out_path)
        self._model = model_name
        self._language = language
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            self.status.emit(f"Loading faster-whisper ({self._model})...")
            path = transcribe_to_srt(
                self._source,
                self._out_path,
                model_name=self._model,
                language=self._language,
                progress_cb=self.progress.emit,
                cancel_cb=lambda: self._cancel,
            )
            if self._cancel:
                self.failed.emit("Cancelled.")
                return
            self.finished_ok.emit(str(path))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
