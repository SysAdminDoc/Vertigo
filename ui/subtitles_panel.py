"""Subtitles tab — AI caption generation with faster-whisper.

Responsibilities kept small: the panel only collects user intent
(toggle burn-in, pick model + language, Transcribe button, Clear button)
and reports a SubtitleChoice back to the main window. The main window
owns the SubtitleWorker lifecycle and fills in the SRT path when ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.caption_styles import PRESETS as CAPTION_PRESETS, default_preset as default_caption_preset
from core.subtitles import AVAILABLE_MODELS, DEFAULT_MODEL


_LANGUAGES: list[tuple[str | None, str]] = [
    (None, "Auto-detect"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("pt", "Portuguese"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
    ("ru", "Russian"),
]


@dataclass(frozen=True)
class SubtitleChoice:
    burn_in: bool
    srt_path: Path | None
    model: str
    language: str | None
    preset_id: str = "pop"


class SubtitlesPanel(QWidget):
    transcribe_requested = pyqtSignal(str, object, str)  # model, lang, preset_id
    clear_requested = pyqtSignal()
    changed = pyqtSignal(object)                          # SubtitleChoice

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._srt_path: Path | None = None
        self._running = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self._toggle = QCheckBox("Burn captions into the exported video")
        self._toggle.setAccessibleName("Toggle subtitle burn-in")
        self._toggle.setToolTip("When enabled, generated captions are baked directly into the exported pixels.")
        self._toggle.toggled.connect(lambda _: self.changed.emit(self._choice()))
        root.addWidget(self._toggle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        model_lbl = QLabel("Model")
        model_lbl.setObjectName("formLabel")
        self._model = QComboBox()
        self._model.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model.setToolTip("Larger models transcribe more accurately but take longer and use more RAM.")
        for name in AVAILABLE_MODELS:
            self._model.addItem(name, name)
        default_idx = self._model.findData(DEFAULT_MODEL)
        if default_idx >= 0:
            self._model.setCurrentIndex(default_idx)
        grid.addWidget(model_lbl, 0, 0)
        grid.addWidget(self._model, 0, 1)

        lang_lbl = QLabel("Language")
        lang_lbl.setObjectName("formLabel")
        self._language = QComboBox()
        self._language.setCursor(Qt.CursorShape.PointingHandCursor)
        for code, name in _LANGUAGES:
            self._language.addItem(name, code)
        grid.addWidget(lang_lbl, 1, 0)
        grid.addWidget(self._language, 1, 1)

        style_lbl = QLabel("Style")
        style_lbl.setObjectName("formLabel")
        self._preset_combo = QComboBox()
        self._preset_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preset_combo.setToolTip("Preset look for burned-in captions")
        for preset in CAPTION_PRESETS.values():
            self._preset_combo.addItem(preset.label, preset.id)
        default_preset_idx = self._preset_combo.findData(default_caption_preset().id)
        if default_preset_idx >= 0:
            self._preset_combo.setCurrentIndex(default_preset_idx)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        grid.addWidget(style_lbl, 2, 0)
        grid.addWidget(self._preset_combo, 2, 1)

        self._preset_hint = QLabel("")
        self._preset_hint.setObjectName("valueMuted")
        self._preset_hint.setWordWrap(True)
        grid.addWidget(self._preset_hint, 3, 0, 1, 2)
        self._refresh_preset_hint()

        root.addLayout(grid)

        self._status = QLabel(
            "Captions are transcribed locally with faster-whisper. "
            "The chosen model downloads the first time you use it."
        )
        self._status.setObjectName("subtitle")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.hide()
        root.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._transcribe_btn = QPushButton("Generate captions")
        self._transcribe_btn.setObjectName("primaryBtn")
        self._transcribe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._transcribe_btn.setToolTip("Transcribe the current clip and save an SRT alongside it")
        self._transcribe_btn.setEnabled(False)
        self._transcribe_btn.clicked.connect(self._emit_transcribe)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("ghostBtn")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setToolTip("Discard captions generated for this clip")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._on_clear)

        btn_row.addWidget(self._transcribe_btn, 1)
        btn_row.addWidget(self._clear_btn)
        root.addLayout(btn_row)
        root.addStretch(1)

    # ------------------------------------------------------------ api
    def set_clip_loaded(self, loaded: bool) -> None:
        self._transcribe_btn.setEnabled(loaded and not self._running)
        if not loaded:
            self._status.setText("Load a clip to enable caption generation.")
            self._reset(keep_toggle=True)

    def set_running(self, running: bool) -> None:
        self._running = running
        self._transcribe_btn.setEnabled(not running and self._transcribe_btn.isEnabled())
        self._transcribe_btn.setText(
            "Transcribing\u2026" if running else "Generate captions"
        )
        if running:
            self._progress.setValue(0)
            self._progress.show()
        else:
            self._progress.hide()

    def set_progress(self, fraction: float) -> None:
        self._progress.setValue(int(max(0.0, min(1.0, fraction)) * 100))

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_srt_path(self, path: Path | None) -> None:
        self._srt_path = path
        self._clear_btn.setEnabled(path is not None)
        if path is None:
            self._status.setText("No captions generated for this clip yet.")
        else:
            self._status.setText(f"Captions ready: {path.name}")
        self.changed.emit(self._choice())

    def choice(self) -> SubtitleChoice:
        return self._choice()

    # ------------------------------------------------------------ impl
    def _choice(self) -> SubtitleChoice:
        return SubtitleChoice(
            burn_in=self._toggle.isChecked(),
            srt_path=self._srt_path,
            model=self._model.currentData(),
            language=self._language.currentData(),
            preset_id=self._preset_combo.currentData() or "pop",
        )

    def _emit_transcribe(self) -> None:
        self.transcribe_requested.emit(
            self._model.currentData(),
            self._language.currentData(),
            self._preset_combo.currentData() or "pop",
        )

    def _on_clear(self) -> None:
        self.set_srt_path(None)
        self.clear_requested.emit()

    def _on_preset_changed(self, *_args) -> None:
        self._refresh_preset_hint()
        self.changed.emit(self._choice())

    def _refresh_preset_hint(self) -> None:
        preset_id = self._preset_combo.currentData() or "pop"
        preset = CAPTION_PRESETS.get(preset_id)
        if preset is None:
            self._preset_hint.setText("")
            return
        if preset.animation == "karaoke":
            extra = "  \u00b7  word-level timings (slower)"
        elif preset.animation == "pop":
            extra = "  \u00b7  per-chunk emphasis"
        else:
            extra = ""
        self._preset_hint.setText(f"{preset.description}{extra}")

    def _reset(self, *, keep_toggle: bool = False) -> None:
        if not keep_toggle:
            self._toggle.setChecked(False)
        self._srt_path = None
        self._clear_btn.setEnabled(False)
        self._progress.hide()
        self.changed.emit(self._choice())
