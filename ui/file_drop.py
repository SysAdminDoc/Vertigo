"""Drag-and-drop import zone — painted empty state, not a placeholder.

Uses QWidget + paintEvent instead of QLabel so the mark (a 9:16 frame
glyph) and text have their own independent typography and spacing.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QFileDialog, QSizePolicy, QWidget

from .theme import current_palette, qcolor


_VIDEO_EXT = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm",
    ".m4v", ".wmv", ".flv", ".ts", ".mpg", ".mpeg",
}

_ACCEPTED_LABEL = "MP4  ·  MOV  ·  MKV  ·  WEBM  ·  AVI"


class FileDropZone(QWidget):
    file_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._hover = False
        self.setAccessibleName("Import videos")
        self.setAccessibleDescription(
            "Drop videos here, click to browse, or press Enter."
        )
        self.setToolTip("Import one or more source videos")

    # ---------------------------------------------- drag-drop
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                if _is_video(u.toLocalFile()):
                    event.acceptProposedAction()
                    self._set_hover(True)
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_hover(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if _is_video(u.toLocalFile())]
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        if len(paths) == 1:
            self.file_dropped.emit(paths[0])
        else:
            self.files_dropped.emit(paths)

    # ---------------------------------------------- input
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_dialog()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._open_dialog()
            event.accept()
            return
        super().keyPressEvent(event)

    def _open_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import video(s)",
            "",
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.flv *.ts *.mpg *.mpeg);;All files (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not paths:
            return
        if len(paths) == 1:
            self.file_dropped.emit(paths[0])
        else:
            self.files_dropped.emit(paths)

    def _set_hover(self, on: bool) -> None:
        if self._hover == on:
            return
        self._hover = on
        self.update()

    # ---------------------------------------------- paint
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        theme = current_palette()
        active = self._hover or self.hasFocus()

        # Surface — inset rounded container with a dashed border.
        container = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        pen = QPen(qcolor(theme.accent if active else theme.surface2))
        pen.setWidthF(1.2 if active else 1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 4])
        p.setPen(pen)
        if active:
            p.setBrush(qcolor(theme.accent_hover))
        else:
            p.setBrush(QColor(theme.base))
        p.drawRoundedRect(container, 14, 14)

        # Centered composition: 9:16 frame glyph + headline + helper text.
        cx = container.center().x()
        cy = container.center().y()

        # Glyph: a 9:16 frame with an inset play triangle.
        glyph_h = min(96.0, container.height() * 0.42)
        glyph_w = glyph_h * 9.0 / 16.0
        glyph_rect = QRectF(cx - glyph_w / 2, cy - glyph_h - 16,
                            glyph_w, glyph_h)

        accent = QColor(theme.accent)
        if not active:
            accent.setAlpha(180)
        frame_pen = QPen(accent)
        frame_pen.setWidthF(1.8)
        p.setPen(frame_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(glyph_rect, 6, 6)

        # Downward arrow into the frame — reinforces the "drop here" gesture.
        arrow_pen = QPen(accent)
        arrow_pen.setWidthF(1.8)
        arrow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arrow_pen)
        arrow_top = glyph_rect.top() - 22
        arrow_tip = glyph_rect.top() + glyph_h * 0.28
        p.drawLine(int(cx), int(arrow_top), int(cx), int(arrow_tip))
        p.drawLine(int(cx), int(arrow_tip),
                   int(cx - 6), int(arrow_tip - 6))
        p.drawLine(int(cx), int(arrow_tip),
                   int(cx + 6), int(arrow_tip - 6))

        # Headline
        headline_font = QFont()
        headline_font.setPointSize(13)
        headline_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(headline_font)
        p.setPen(QColor(theme.text))
        headline_rect = QRect(
            int(container.left()),
            int(cy + 10),
            int(container.width()),
            26,
        )
        headline = "Release to add clips" if self._hover else "Drop videos here to begin"
        p.drawText(headline_rect, Qt.AlignmentFlag.AlignHCenter, headline)

        # Helper: click + shortcut + formats
        helper_font = QFont()
        helper_font.setPointSize(10)
        helper_font.setWeight(QFont.Weight.Normal)
        p.setFont(helper_font)
        p.setPen(QColor(theme.subtext0))
        helper_rect = QRect(
            int(container.left()),
            int(cy + 36),
            int(container.width()),
            20,
        )
        helper = (
            "Accepted formats  ·  " + _ACCEPTED_LABEL
            if self._hover
            else "Click anywhere to browse  ·  Enter to open dialog"
        )
        p.drawText(helper_rect, Qt.AlignmentFlag.AlignHCenter, helper)

        # Format list as a faint caption at the bottom
        if not self._hover:
            caption_font = QFont()
            caption_font.setPointSize(9)
            caption_font.setWeight(QFont.Weight.Normal)
            caption_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
            p.setFont(caption_font)
            p.setPen(QColor(theme.overlay1))
            p.drawText(
                QRect(
                    int(container.left()),
                    int(container.bottom() - 28),
                    int(container.width()),
                    20,
                ),
                Qt.AlignmentFlag.AlignHCenter,
                _ACCEPTED_LABEL,
            )

        p.end()


def _is_video(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_EXT
