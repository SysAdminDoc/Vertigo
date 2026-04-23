"""Animated drag-and-drop file zone."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QFileDialog, QLabel, QWidget


_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".ts", ".mpg", ".mpeg"}


class FileDropZone(QLabel):
    file_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)  # list[str]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idle_text = (
            "\u2B8B\n\n"
            "Drop source videos here\n\n"
            "Click to browse, or press Enter. MP4 · MOV · MKV · AVI · WEBM"
        )
        self._hover_text = (
            "\u2B8B\n\n"
            "Release to add clips\n\n"
            "Accepted videos will appear in the queue."
        )
        self.setText(self._idle_text)
        self.setMinimumHeight(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("hover", "false")
        self.setToolTip("Import one or more source videos")
        self.setAccessibleName("Import videos")
        self.setAccessibleDescription("Drop videos here, click to browse, or press Enter.")

    # drag-drop --------------------------------------------------------
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
        self.setProperty("hover", "true" if on else "false")
        self.setText(self._hover_text if on else self._idle_text)
        self.style().unpolish(self)
        self.style().polish(self)


def _is_video(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_EXT
