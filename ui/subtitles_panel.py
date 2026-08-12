"""Subtitles tab — AI caption generation with faster-whisper.

Responsibilities kept small: the panel only collects user intent
(toggle burn-in, pick model + language, Transcribe button, Clear button)
and reports a SubtitleChoice back to the main window. The main window
owns the SubtitleWorker lifecycle and fills in the SRT path when ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.animated_captions import (
    available_templates as animated_available_templates,
    is_available as animated_is_available,
)
from core.caption_styles import PRESETS as CAPTION_PRESETS, default_preset as default_caption_preset
from core.caption_editing import (
    CaptionEditError,
    merge_captions,
    shift_captions,
    split_captions,
)
from core.caption_types import Caption
from core.subtitles import AVAILABLE_MODELS, DEFAULT_MODEL


_PYCAPS_PREFIX = "pycaps:"
_PYCAPS_DISABLED_DATA = "__pycaps_unavailable__"


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
    face_aware: bool = False


class SubtitlesPanel(QWidget):
    transcribe_requested = pyqtSignal(str, object, str, bool)  # model, lang, preset_id, face_aware
    clear_requested = pyqtSignal()
    changed = pyqtSignal(object)                                # SubtitleChoice
    save_caption_edits_requested = pyqtSignal(object)            # list[Caption]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._srt_path: Path | None = None
        self._running = False
        self._clip_loaded = False
        self._captions: list[Caption] = []
        self._review_dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self._toggle = QCheckBox("Burn captions into the exported video")
        self._toggle.setAccessibleName("Toggle subtitle burn-in")
        self._toggle.setToolTip("When enabled, generated captions are baked directly into the exported pixels.")
        self._toggle.toggled.connect(lambda _: self.changed.emit(self._choice()))
        self._toggle.toggled.connect(lambda _: self._refresh_status())
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

        # Animated (pycaps) options. When the package is installed we
        # add one entry per supported template, each carrying the
        # "pycaps:<name>" id so the controller can route the post-
        # encode pycaps render. When it isn't installed we add a
        # single disabled entry so users discover the capability
        # and see the install hint.
        if animated_is_available():
            self._preset_combo.insertSeparator(self._preset_combo.count())
            for template in animated_available_templates():
                self._preset_combo.addItem(
                    f"Animated \u00b7 {template}", f"{_PYCAPS_PREFIX}{template}"
                )
        else:
            self._preset_combo.insertSeparator(self._preset_combo.count())
            idx = self._preset_combo.count()
            self._preset_combo.addItem(
                "Animated (install pycaps to unlock)",
                _PYCAPS_DISABLED_DATA,
            )
            # Grey the placeholder out so users can't select it.
            model = self._preset_combo.model()
            item = model.item(idx) if hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(False)

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

        self._face_aware = QCheckBox("Lift captions off faces (face-aware placement)")
        self._face_aware.setAccessibleName("Toggle face-aware caption positioning")
        self._face_aware.setToolTip(
            "Sample faces at 2 fps and flip captions to the top of the frame when "
            "the default bottom position would cover a subject. No effect on Blur "
            "Letterbox mode (captions sit over the blurred bar)."
        )
        self._face_aware.toggled.connect(lambda _: self.changed.emit(self._choice()))
        root.addWidget(self._face_aware)

        self._status = QLabel("")
        self._status.setObjectName("inlineNotice")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.hide()
        root.addWidget(self._progress)

        self._review_title = QLabel("Timing review")
        self._review_title.setObjectName("formLabel")
        root.addWidget(self._review_title)

        self._review_list = QListWidget()
        self._review_list.setObjectName("captionReviewList")
        self._review_list.setAccessibleName("Caption timing review")
        self._review_list.setToolTip(
            "Select a caption chunk to preview its timing and make a small correction."
        )
        self._review_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._review_list.setMinimumHeight(120)
        self._review_list.setMaximumHeight(220)
        self._review_list.itemSelectionChanged.connect(
            self._on_review_selection_changed
        )
        root.addWidget(self._review_list)

        review_spin_row = QHBoxLayout()
        review_spin_row.setSpacing(8)
        nudge_label = QLabel("Nudge")
        nudge_label.setObjectName("formLabel")
        review_spin_row.addWidget(nudge_label)
        self._nudge_amount = QDoubleSpinBox()
        self._nudge_amount.setObjectName("captionNudgeAmount")
        self._nudge_amount.setAccessibleName("Caption nudge amount")
        self._nudge_amount.setRange(-5.0, 5.0)
        self._nudge_amount.setDecimals(2)
        self._nudge_amount.setSingleStep(0.05)
        self._nudge_amount.setValue(0.25)
        self._nudge_amount.setSuffix(" s")
        self._nudge_amount.setToolTip("Small timing offset applied to the selected chunk or all chunks")
        review_spin_row.addWidget(self._nudge_amount)
        split_label = QLabel("Split at")
        split_label.setObjectName("formLabel")
        review_spin_row.addWidget(split_label)
        self._split_at = QDoubleSpinBox()
        self._split_at.setObjectName("captionSplitPosition")
        self._split_at.setAccessibleName("Caption split position")
        self._split_at.setRange(0.0, 86400.0)
        self._split_at.setDecimals(2)
        self._split_at.setSingleStep(0.1)
        self._split_at.setSuffix(" s")
        self._split_at.setToolTip("Absolute timeline position used by Split selected")
        review_spin_row.addWidget(self._split_at)
        review_spin_row.addStretch(1)
        root.addLayout(review_spin_row)

        review_btn_row = QHBoxLayout()
        review_btn_row.setSpacing(8)
        self._nudge_selected_btn = QPushButton("Nudge selected")
        self._nudge_selected_btn.setObjectName("ghostBtn")
        self._nudge_selected_btn.setAccessibleName("Nudge selected caption")
        self._nudge_selected_btn.setToolTip("Shift only the selected caption chunk")
        self._nudge_selected_btn.clicked.connect(self.nudge_selected)
        review_btn_row.addWidget(self._nudge_selected_btn)
        self._nudge_all_btn = QPushButton("Nudge all")
        self._nudge_all_btn.setObjectName("ghostBtn")
        self._nudge_all_btn.setAccessibleName("Nudge all captions")
        self._nudge_all_btn.setToolTip("Shift every caption chunk by the nudge amount")
        self._nudge_all_btn.clicked.connect(self.nudge_all)
        review_btn_row.addWidget(self._nudge_all_btn)
        root.addLayout(review_btn_row)

        review_edit_row = QHBoxLayout()
        review_edit_row.setSpacing(8)
        self._split_btn = QPushButton("Split selected")
        self._split_btn.setObjectName("ghostBtn")
        self._split_btn.setAccessibleName("Split selected caption")
        self._split_btn.setToolTip("Split the selected chunk into two at the chosen position")
        self._split_btn.clicked.connect(self.split_selected)
        review_edit_row.addWidget(self._split_btn)
        self._merge_btn = QPushButton("Merge with next")
        self._merge_btn.setObjectName("ghostBtn")
        self._merge_btn.setAccessibleName("Merge selected caption with next")
        self._merge_btn.setToolTip("Join the selected chunk with the following chunk")
        self._merge_btn.clicked.connect(self.merge_selected)
        review_edit_row.addWidget(self._merge_btn)
        self._save_review_btn = QPushButton("Save timing")
        self._save_review_btn.setObjectName("primaryBtn")
        self._save_review_btn.setAccessibleName("Save caption timing edits")
        self._save_review_btn.setToolTip("Write the adjusted timing back to the caption sidecar")
        self._save_review_btn.clicked.connect(self.save_caption_edits)
        review_edit_row.addWidget(self._save_review_btn)
        root.addLayout(review_edit_row)

        self._review_status = QLabel("")
        self._review_status.setObjectName("valueMuted")
        self._review_status.setWordWrap(True)
        root.addWidget(self._review_status)

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
        self._sync_controls()
        self._refresh_status()

    # ------------------------------------------------------------ api
    def set_clip_loaded(self, loaded: bool) -> None:
        self._clip_loaded = loaded
        if not loaded:
            self._reset(keep_toggle=False)
        self._sync_controls()
        self._refresh_status()

    def set_running(self, running: bool) -> None:
        self._running = running
        self._transcribe_btn.setText(
            "Transcribing\u2026" if running else "Generate captions"
        )
        if running:
            self._progress.setValue(0)
            self._progress.show()
        else:
            self._progress.hide()
        self._sync_controls()
        self._refresh_status()

    def set_progress(self, fraction: float) -> None:
        self._progress.setValue(int(max(0.0, min(1.0, fraction)) * 100))

    def set_status(self, text: str, tone: str | None = "accent") -> None:
        self._set_status(text, tone=tone)

    def set_srt_path(self, path: Path | None) -> None:
        self._srt_path = path
        if path is None:
            self._toggle.setChecked(False)
            self._set_captions([], dirty=False)
        self._sync_controls()
        self._refresh_status()
        self.changed.emit(self._choice())

    def set_captions(self, captions: list[Caption] | tuple[Caption, ...]) -> None:
        """Show the transcript chunks returned by the worker."""

        self._set_captions(list(captions), dirty=False)

    def captions(self) -> list[Caption]:
        """Return a copy of the currently reviewed transcript."""

        return list(self._captions)

    def preview_at(self, seconds: float) -> None:
        """Select the chunk under the player playhead, if there is one."""

        try:
            position = float(seconds)
        except (TypeError, ValueError):
            return
        for index, caption in enumerate(self._captions):
            if caption.start <= position <= caption.end:
                self._review_list.setCurrentRow(index)
                item = self._review_list.currentItem()
                if item is not None:
                    self._review_list.scrollToItem(item)
                return

    def nudge_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            self._set_review_status("Select a caption chunk first.", tone="warning")
            return
        self._apply_edit(
            shift_captions(self._captions, self._nudge_amount.value(), indices=[index]),
            index=index,
        )

    def nudge_all(self) -> None:
        if not self._captions:
            return
        self._apply_edit(shift_captions(self._captions, self._nudge_amount.value()))

    def split_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            self._set_review_status("Select a caption chunk first.", tone="warning")
            return
        try:
            edited = split_captions(self._captions, index, self._split_at.value())
        except (CaptionEditError, IndexError) as exc:
            self._set_review_status(str(exc), tone="warning")
            return
        self._apply_edit(edited, index=index)

    def merge_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            self._set_review_status("Select a caption chunk first.", tone="warning")
            return
        try:
            edited = merge_captions(self._captions, index)
        except IndexError as exc:
            self._set_review_status(str(exc), tone="warning")
            return
        self._apply_edit(edited, index=min(index, len(edited) - 1))

    def save_caption_edits(self) -> None:
        if not self._review_dirty:
            self._set_review_status("No unsaved timing changes.")
            return
        if self._srt_path is None:
            self._set_review_status("Generate captions before saving timing edits.", tone="warning")
            return
        self.save_caption_edits_requested.emit(list(self._captions))

    def mark_caption_edits_saved(self) -> None:
        self._review_dirty = False
        self._set_review_status("Timing edits saved to the caption sidecar.", tone="success")
        self._sync_controls()

    def mark_caption_edits_failed(self, message: str) -> None:
        self._review_dirty = True
        self._set_review_status(message, tone="warning")
        self._sync_controls()

    def choice(self) -> SubtitleChoice:
        return self._choice()

    # ------------------------------------------------------------ impl
    def _choice(self) -> SubtitleChoice:
        preset_id = self._preset_combo.currentData() or "pop"
        # If the disabled placeholder somehow got selected (shouldn't
        # be possible via keyboard, but defensive), fall back to the
        # default preset so the encode pipeline stays on a real id.
        if preset_id == _PYCAPS_DISABLED_DATA:
            preset_id = "pop"
        return SubtitleChoice(
            burn_in=self._toggle.isChecked(),
            srt_path=self._srt_path,
            model=self._model.currentData(),
            language=self._language.currentData(),
            preset_id=preset_id,
            face_aware=self._face_aware.isChecked(),
        )

    def _emit_transcribe(self) -> None:
        preset_id = self._preset_combo.currentData() or "pop"
        if preset_id == _PYCAPS_DISABLED_DATA:
            preset_id = "pop"
        self.transcribe_requested.emit(
            self._model.currentData(),
            self._language.currentData(),
            preset_id,
            self._face_aware.isChecked(),
        )

    def _on_clear(self) -> None:
        self.set_srt_path(None)
        self.clear_requested.emit()

    def _on_preset_changed(self, *_args) -> None:
        self._refresh_preset_hint()
        self.changed.emit(self._choice())

    def _refresh_preset_hint(self) -> None:
        preset_id = self._preset_combo.currentData() or "pop"
        if isinstance(preset_id, str) and preset_id.startswith(_PYCAPS_PREFIX):
            template = preset_id[len(_PYCAPS_PREFIX):]
            self._preset_hint.setText(
                f"pycaps template: {template}. Runs as a second encode "
                "pass after the main export, so the final file is longer "
                "to produce than a libass burn-in."
            )
            return
        if preset_id == _PYCAPS_DISABLED_DATA:
            self._preset_hint.setText(
                "Install pycaps to enable per-word animated captions:  "
                "pip install pycaps"
            )
            return
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
            self._face_aware.setChecked(False)
        self._srt_path = None
        self._set_captions([], dirty=False)
        self._progress.hide()
        self._sync_controls()
        self._refresh_status()
        self.changed.emit(self._choice())

    def _sync_controls(self) -> None:
        has_captions = self._srt_path is not None
        can_edit = self._clip_loaded and not self._running
        self._model.setEnabled(can_edit)
        self._language.setEnabled(can_edit)
        self._preset_combo.setEnabled(can_edit)
        self._face_aware.setEnabled(can_edit)
        self._transcribe_btn.setEnabled(can_edit)
        self._clear_btn.setEnabled(self._clip_loaded and has_captions and not self._running)
        self._toggle.setEnabled(self._clip_loaded and has_captions and not self._running)
        review_editable = can_edit and bool(self._captions)
        self._review_title.setVisible(bool(self._captions))
        self._review_list.setVisible(bool(self._captions))
        self._nudge_amount.setVisible(bool(self._captions))
        self._split_at.setVisible(bool(self._captions))
        self._nudge_selected_btn.setVisible(bool(self._captions))
        self._nudge_all_btn.setVisible(bool(self._captions))
        self._split_btn.setVisible(bool(self._captions))
        self._merge_btn.setVisible(bool(self._captions))
        self._save_review_btn.setVisible(bool(self._captions))
        self._review_status.setVisible(bool(self._captions) or bool(self._review_status.text()))
        for control in (
            self._review_list,
            self._nudge_amount,
            self._split_at,
            self._nudge_selected_btn,
            self._nudge_all_btn,
            self._split_btn,
            self._merge_btn,
        ):
            control.setEnabled(review_editable)
        self._save_review_btn.setEnabled(
            review_editable and self._review_dirty and has_captions
        )

    def _refresh_status(self) -> None:
        if self._running:
            model = self._model.currentData()
            preset_label = self._preset_combo.currentText()
            self._set_status(
                f"Transcribing locally with whisper-{model}. Captions will be styled as {preset_label}.",
                tone="accent",
            )
            return

        if not self._clip_loaded:
            self._set_status(
                "Load a clip to generate captions, choose a style, and optionally burn them into the export.",
            )
            return

        if self._srt_path is None:
            self._set_status(
                "Captions are transcribed locally with faster-whisper. Generate them once, then choose whether to burn them into the export.",
            )
            return

        burn = "Burn-in enabled for export." if self._toggle.isChecked() else "Enable burn-in when you want them baked into the export."
        self._set_status(f"Captions ready: {self._srt_path.name}. {burn}", tone="success")

    def _set_status(self, text: str, tone: str | None = None) -> None:
        self._status.setText(text)
        self._status.setProperty("tone", tone)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    # --------------------------------------------------------- review impl
    def _set_captions(self, captions: list[Caption], *, dirty: bool) -> None:
        self._captions = list(captions)
        self._review_dirty = dirty
        self._rebuild_review_list()
        if not self._captions:
            self._review_status.clear()
        self._sync_controls()

    def _apply_edit(self, captions: list[Caption], *, index: int | None = None) -> None:
        self._set_captions(captions, dirty=True)
        if self._captions:
            selected = max(0, min(index if index is not None else 0, len(self._captions) - 1))
            self._review_list.setCurrentRow(selected)
        self._set_review_status(
            "Unsaved timing changes. Save timing to update the export sidecar."
        )

    def _rebuild_review_list(self) -> None:
        selected = self._selected_index()
        with QSignalBlocker(self._review_list):
            self._review_list.clear()
            for index, caption in enumerate(self._captions):
                item = QListWidgetItem(
                    f"{index + 1:02d}  {_time_label(caption.start)} → "
                    f"{_time_label(caption.end)}\n{caption.text}"
                )
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(
                    f"{_time_label(caption.start)} → {_time_label(caption.end)}\n"
                    f"{caption.text}"
                )
                self._review_list.addItem(item)
            if self._captions:
                row = max(0, min(selected if selected is not None else 0, len(self._captions) - 1))
                self._review_list.setCurrentRow(row)
        self._on_review_selection_changed()

    def _selected_index(self) -> int | None:
        row = self._review_list.currentRow()
        return row if 0 <= row < len(self._captions) else None

    def _on_review_selection_changed(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        caption = self._captions[index]
        with QSignalBlocker(self._split_at):
            self._split_at.setValue((caption.start + caption.end) / 2.0)

    def _set_review_status(self, text: str, *, tone: str | None = None) -> None:
        self._review_status.setText(text)
        self._review_status.setProperty("tone", tone)
        self._review_status.style().unpolish(self._review_status)
        self._review_status.style().polish(self._review_status)
        self._review_status.setVisible(bool(text))


def _time_label(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"
