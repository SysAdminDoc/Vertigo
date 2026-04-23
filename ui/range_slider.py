"""Dual-thumb range slider — used as an in/out trim selector on the timeline.

Emits `range_changed(low_sec, high_sec)` live during drag, and draws the
playhead as a third marker when `set_playhead(sec)` is called.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .theme import current_palette


class RangeSlider(QWidget):
    range_changed = pyqtSignal(float, float)
    playhead_seek = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Trim timeline")

        self._duration: float = 0.0
        self._low: float = 0.0
        self._high: float = 0.0
        self._playhead: float = 0.0
        self._drag: str | None = None  # "low" | "high" | "playhead" | None

    def set_duration(self, d: float) -> None:
        self._duration = max(0.0, d)
        self._low = 0.0
        self._high = self._duration
        self._playhead = 0.0
        self.update()
        self.range_changed.emit(self._low, self._high)

    def reset(self) -> None:
        self._duration = 0.0
        self._low = 0.0
        self._high = 0.0
        self._playhead = 0.0
        self._drag = None
        self.update()

    def set_playhead(self, t: float) -> None:
        self._playhead = max(0.0, min(self._duration, t))
        self.update()

    def low(self) -> float:
        return self._low

    def high(self) -> float:
        return self._high

    def duration(self) -> float:
        return self._duration

    # -------------------------------------------------- painting
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = current_palette()

        track_rect = QRectF(10, self.height() / 2 - 3, self.width() - 20, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.surface0))
        p.drawRoundedRect(track_rect, 3, 3)

        if self._duration <= 0:
            if self.hasFocus():
                p.setPen(QPen(QColor(theme.focus), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 8, 8)
            p.end()
            return

        lo_x = self._t_to_x(self._low)
        hi_x = self._t_to_x(self._high)
        sel_rect = QRectF(lo_x, track_rect.top(), hi_x - lo_x, track_rect.height())
        p.setBrush(QColor(theme.accent))
        p.drawRoundedRect(sel_rect, 3, 3)

        # playhead
        ph_x = self._t_to_x(self._playhead)
        p.setPen(QPen(QColor(theme.text), 2))
        p.drawLine(int(ph_x), 6, int(ph_x), self.height() - 6)

        # thumbs
        self._paint_thumb(p, lo_x, is_high=False)
        self._paint_thumb(p, hi_x, is_high=True)

        if self.hasFocus():
            p.setPen(QPen(QColor(theme.focus), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 8, 8)

        p.end()

    def _paint_thumb(self, p: QPainter, x: float, *, is_high: bool) -> None:
        size = 14
        theme = current_palette()
        r = QRectF(x - size / 2, self.height() / 2 - size / 2, size, size)
        p.setPen(QPen(QColor(theme.accent), 2))
        p.setBrush(QColor(theme.text))
        p.drawEllipse(r)
        # edge glyph
        p.setPen(QPen(QColor(theme.crust), 2))
        mx = r.center().x()
        my = r.center().y()
        if is_high:
            p.drawLine(int(mx - 3), int(my - 4), int(mx - 3), int(my + 4))
        else:
            p.drawLine(int(mx + 3), int(my - 4), int(mx + 3), int(my + 4))

    # -------------------------------------------------- mouse
    def mousePressEvent(self, event) -> None:
        if self._duration <= 0:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        x = event.position().x()
        lo_x = self._t_to_x(self._low)
        hi_x = self._t_to_x(self._high)

        if abs(x - lo_x) < 10:
            self._drag = "low"
        elif abs(x - hi_x) < 10:
            self._drag = "high"
        else:
            self._drag = "playhead"
            self._playhead = self._x_to_t(x)
            self.playhead_seek.emit(self._playhead)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._drag or self._duration <= 0:
            if self._duration > 0:
                x = event.position().x()
                near_thumb = abs(x - self._t_to_x(self._low)) < 12 or abs(x - self._t_to_x(self._high)) < 12
                self.setCursor(Qt.CursorShape.SizeHorCursor if near_thumb else Qt.CursorShape.PointingHandCursor)
            return
        t = self._x_to_t(event.position().x())
        if self._drag == "low":
            self._low = max(0.0, min(t, self._high - 0.1))
            self.range_changed.emit(self._low, self._high)
        elif self._drag == "high":
            self._high = min(self._duration, max(t, self._low + 0.1))
            self.range_changed.emit(self._low, self._high)
        elif self._drag == "playhead":
            self._playhead = t
            self.playhead_seek.emit(t)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def keyPressEvent(self, event) -> None:
        if self._duration <= 0:
            super().keyPressEvent(event)
            return

        step = 5.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        if event.key() == Qt.Key.Key_Left:
            self._playhead = max(0.0, self._playhead - step)
        elif event.key() == Qt.Key.Key_Right:
            self._playhead = min(self._duration, self._playhead + step)
        elif event.key() == Qt.Key.Key_Home:
            self._playhead = 0.0
        elif event.key() == Qt.Key.Key_End:
            self._playhead = self._duration
        else:
            super().keyPressEvent(event)
            return
        self.playhead_seek.emit(self._playhead)
        self.update()
        event.accept()

    # -------------------------------------------------- helpers
    def _t_to_x(self, t: float) -> float:
        if self._duration <= 0:
            return 10.0
        return 10 + (self.width() - 20) * (t / self._duration)

    def _x_to_t(self, x: float) -> float:
        x = max(10, min(self.width() - 10, x))
        return (x - 10) / max(1, self.width() - 20) * self._duration
