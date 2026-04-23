"""Output settings panel — encoder pick, quality slider, speed preset.

Surfaces every available FFmpeg encoder we detect on the system so power
users can pin a specific GPU pipeline (NVENC / QuickSync / AMF /
VideoToolbox) and dial in quality vs. size.

Exposes `current_selection()` returning a dataclass the main window feeds
into EncodeJob.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.encoders import Encoder, all_available, pick_default


@dataclass(frozen=True)
class OutputChoice:
    encoder: Encoder | None
    quality: int
    speed_preset: str | None


class OutputPanel(QWidget):
    changed = pyqtSignal(object)  # OutputChoice

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._encoders: list[Encoder] = all_available()

        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setHorizontalSpacing(10)
        lay.setVerticalSpacing(10)

        # encoder -------------------------------------------------------
        self._encoder_combo = QComboBox()
        self._encoder_combo.setAccessibleName("Video encoder")
        self._encoder_combo.setToolTip("Choose the encoder FFmpeg will use")
        self._encoder_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._encoders:
            for enc in self._encoders:
                tag = "  \u2605 GPU" if enc.hardware else "  \u00b7 CPU"
                self._encoder_combo.addItem(enc.label + tag, enc)
            default = pick_default("h264") or self._encoders[0]
            idx = next(
                (i for i, e in enumerate(self._encoders) if e.id == default.id),
                0,
            )
            self._encoder_combo.setCurrentIndex(idx)
        else:
            self._encoder_combo.addItem("No encoders found", None)
            self._encoder_combo.setEnabled(False)
        self._encoder_combo.currentIndexChanged.connect(self._on_encoder_changed)

        self._add_row(lay, 0, "Encoder", self._encoder_combo, None)

        # quality -------------------------------------------------------
        self._quality = QSlider(Qt.Orientation.Horizontal)
        self._quality.setRange(1, 100)
        self._quality.setValue(75)
        self._quality.setPageStep(5)
        self._quality.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._quality.setToolTip("Higher = better quality, bigger file")
        self._quality.setAccessibleName("Output quality")

        self._quality_v = QLabel("75")
        self._quality_v.setObjectName("formValue")
        self._quality_v.setFixedWidth(48)
        self._quality_v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._add_row(lay, 1, "Quality", self._quality, self._quality_v)
        self._quality.valueChanged.connect(self._on_quality_changed)

        # speed preset --------------------------------------------------
        self._speed_combo = QComboBox()
        self._speed_combo.setAccessibleName("Encoder speed preset")
        self._speed_combo.setToolTip("Encoding speed vs. efficiency")
        self._speed_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_row(lay, 2, "Speed", self._speed_combo, None)
        self._speed_combo.currentIndexChanged.connect(self._emit_change)

        # status line ---------------------------------------------------
        self._status = QLabel("")
        self._status.setObjectName("subtitle")
        self._status.setWordWrap(True)
        lay.addWidget(self._status, 3, 0, 1, 3)

        # hardware summary ---------------------------------------------
        self._summary = QLabel("")
        self._summary.setObjectName("valueMuted")
        self._summary.setWordWrap(True)
        lay.addWidget(self._summary, 4, 0, 1, 3)

        self._refresh_summary()
        self._on_encoder_changed()

    # ------------------------------------------------------------ api
    def current_selection(self) -> OutputChoice:
        enc = self._encoder_combo.currentData()
        speed = self._speed_combo.currentData()
        return OutputChoice(encoder=enc, quality=self._quality.value(), speed_preset=speed)

    # ------------------------------------------------------------ impl
    def _on_encoder_changed(self) -> None:
        enc: Encoder | None = self._encoder_combo.currentData()
        self._speed_combo.blockSignals(True)
        self._speed_combo.clear()
        if enc and enc.preset_values:
            for preset in enc.preset_values:
                self._speed_combo.addItem(preset, preset)
            if enc.preset_default:
                idx = self._speed_combo.findData(enc.preset_default)
                if idx >= 0:
                    self._speed_combo.setCurrentIndex(idx)
            self._speed_combo.setEnabled(True)
        else:
            self._speed_combo.addItem("Not adjustable", None)
            self._speed_combo.setEnabled(False)
        self._speed_combo.blockSignals(False)

        if enc:
            self._quality.setValue(enc.quality_default)
            tone = "GPU-accelerated" if enc.hardware else "Software (CPU)"
            self._status.setText(f"{enc.label} \u2014 {tone}.  Codec: {enc.codec.upper()}.")
        else:
            self._status.setText("No encoder available. Install FFmpeg.")

        self._emit_change()

    def _on_quality_changed(self, value: int) -> None:
        self._quality_v.setText(str(value))
        self._emit_change()

    def _emit_change(self) -> None:
        self.changed.emit(self.current_selection())

    def _refresh_summary(self) -> None:
        if not self._encoders:
            self._summary.setText("No video encoders detected.")
            return
        gpu = [e.label for e in self._encoders if e.hardware]
        cpu = [e.label for e in self._encoders if not e.hardware]
        parts: list[str] = []
        if gpu:
            parts.append("GPU: " + ", ".join(e.split(" (")[0] for e in gpu))
        if cpu:
            parts.append("CPU: libx264 / libx265")
        self._summary.setText("  \u00b7  ".join(parts))

    def _add_row(self, lay: QGridLayout, row: int, title: str, widget: QWidget, value: QLabel | None) -> None:
        t = QLabel(title)
        t.setObjectName("formLabel")
        lay.addWidget(t, row, 0)
        lay.addWidget(widget, row, 1)
        if value is not None:
            lay.addWidget(value, row, 2)
