"""QThread that runs faster-whisper off the UI thread.

Output format is selected by the active caption preset:

  * preset.animation == "karaoke" with word-level timings → .ass with
    \\kf per-word sweep tags
  * anything else → .srt (libass applies force_style at burn-in time)

When ``animated_style`` is set (a pycaps style identifier), the worker
additionally renders a transparent animated caption overlay MOV using
``core.animated_captions``. The MOV is emitted via the
``overlay_ready`` signal *after* the base subtitle file is available,
so callers can pipe it straight into an encode job's ``overlay_video``
field. Whisper is only run once regardless — word-level timings are
forced so the pycaps renderer has what it needs.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.caption_styles import CaptionPreset, default_preset
from core.subtitles import DEFAULT_MODEL, transcribe_and_write


class SubtitleWorker(QThread):
    progress = pyqtSignal(float)           # 0..1
    status = pyqtSignal(str)               # log line
    finished_ok = pyqtSignal(str)          # final subtitle file path
    overlay_ready = pyqtSignal(str)        # pycaps overlay MOV path (optional)
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
        animated_style: str | None = None,
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
        self._animated_style = animated_style
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            face_note = "  \u00b7  face-aware layout" if self._face_aware and not self._letterbox else ""
            animated_note = (
                f"  \u00b7  animated ({self._animated_style})"
                if self._animated_style else ""
            )
            self.status.emit(
                f"Loading faster-whisper ({self._model}) \u2014 "
                f"{self._preset.label} preset{face_note}{animated_note}"
            )
            if self._face_aware and not self._letterbox:
                self.status.emit("Sampling faces for caption placement\u2026")

            result = transcribe_and_write(
                self._source,
                self._out_dir,
                preset=self._preset,
                height_px=self._height,
                model_name=self._model,
                language=self._language,
                face_aware=self._face_aware,
                letterbox=self._letterbox,
                # pycaps needs word-level timings regardless of preset.
                force_word_level=bool(self._animated_style),
                progress_cb=self.progress.emit,
                cancel_cb=lambda: self._cancel,
            )
            if self._cancel:
                self.failed.emit("Cancelled.")
                return

            # Emit the base SRT/ASS first so the caption panel can show
            # the user it's ready even if the animated render takes a
            # moment longer.
            self.finished_ok.emit(str(result.path))

            if self._animated_style:
                self._render_animated(result.captions)
        except Exception as e:
            if self._cancel:
                self.failed.emit("Cancelled.")
            else:
                self.failed.emit(f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    def _render_animated(self, captions: list) -> None:
        """Render a pycaps RGBA overlay MOV from ``captions``.

        Failures here must NOT raise back to ``run`` — the base SRT/ASS
        has already been emitted and the encode pipeline can use that
        path as a fallback. We surface the failure as a status line
        instead so the user understands why no overlay appeared.
        """
        from core import animated_captions

        if not animated_captions.is_available():
            self.status.emit(
                "pycaps not installed — animated overlay skipped."
            )
            return
        self.status.emit("Rendering animated caption overlay\u2026")
        try:
            result = animated_captions.render(
                captions,
                out_dir=self._out_dir,
                source_video=self._source,
                style=self._animated_style or animated_captions.DEFAULT_STYLE,
                cancel_cb=lambda: self._cancel,
            )
        except Exception as e:
            self.status.emit(f"Animated overlay failed: {e}")
            return
        if self._cancel:
            return
        self.overlay_ready.emit(str(result.overlay_path))
