"""Shared premium widgets — panel, mode card, and toast feedback."""

from __future__ import annotations

from PyQt6.QtCore import (
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import current_palette


class GlassPanel(QFrame):
    """Quiet rounded panel with optional section title."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(18, 16, 18, 16)
        self._outer.setSpacing(12)

        if title:
            lbl = QLabel(title)
            lbl.setObjectName("sectionTitle")
            self._outer.addWidget(lbl)

    def add(self, w: QWidget) -> None:
        self._outer.addWidget(w)

    def layout(self) -> QVBoxLayout:
        return self._outer


class ModeCard(QPushButton):
    """Toggleable card for a reframe mode."""

    def __init__(
        self,
        icon_char: str,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modeCard")
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(subtitle)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        self._icon = QLabel(icon_char)
        self._icon.setFixedWidth(32)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._title = QLabel(title)
        self._subtitle = QLabel(subtitle)
        self._subtitle.setWordWrap(True)
        text_col.addWidget(self._title)
        text_col.addWidget(self._subtitle)
        lay.addLayout(text_col, 1)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        theme = current_palette()
        self._icon.setStyleSheet(f"color: {theme.accent}; font-size: 22px; font-weight: 700;")
        self._title.setStyleSheet(f"color: {theme.text}; font-size: 13px; font-weight: 700;")
        self._subtitle.setStyleSheet(f"color: {theme.subtext0}; font-size: 11px;")


class Toast(QLabel):
    """Transient floating message."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._kind = "info"
        self._apply_style()
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(250)

    def show_toast(self, text: str, duration_ms: int = 2200, kind: str = "info") -> None:
        self._kind = kind
        self._apply_style()
        self.setText("  " + text + "  ")
        self.adjustSize()
        p = self.parent()
        if isinstance(p, QWidget):
            x = (p.width() - self.width()) // 2
            y = p.height() - self.height() - 48
            self.move(x, y)
        self.setWindowOpacity(0.0)
        self.show()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(duration_ms)

    def _apply_style(self) -> None:
        colors = {
            "success": current_palette().green,
            "warning": current_palette().yellow,
            "error": current_palette().red,
            "info": current_palette().accent,
        }
        theme = current_palette()
        accent = colors.get(self._kind, theme.accent)
        self.setStyleSheet(
            f"background: {theme.surface0};"
            f"color: {theme.text};"
            f"border: 1px solid {accent};"
            f"border-radius: 8px;"
            f"padding: 10px 16px; font-size: 12px; font-weight: 600;"
        )

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._hide_once)
        self._fade.start()

    def _hide_once(self) -> None:
        try:
            self._fade.finished.disconnect(self._hide_once)
        except TypeError:
            pass
        self.hide()

    def refresh_theme(self) -> None:
        self._apply_style()
