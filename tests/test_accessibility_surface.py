"""Accessibility smoke coverage for the live PyQt workspace."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


class AccessibilitySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication(sys.argv)
        from ui.theme import apply_app_theme

        apply_app_theme(cls._app, "mocha")

    def test_interactive_surface_has_name_and_focus_policy(self) -> None:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QAbstractButton,
            QAbstractSlider,
            QAbstractSpinBox,
            QComboBox,
            QLineEdit,
            QScrollBar,
        )
        from ui.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            win = MainWindow()
            try:
                # Exercise controls that are only created for non-empty states.
                win._overlays_panel._add_preset("intro")
                win._queue.add(Path(tmp) / "queued.mp4")

                native_controls = (
                    QAbstractButton,
                    QAbstractSlider,
                    QAbstractSpinBox,
                    QComboBox,
                    QLineEdit,
                )
                for widget in win.findChildren(native_controls):
                    # These are Qt implementation details, not app controls.
                    if isinstance(widget, QScrollBar):
                        continue
                    if isinstance(widget, QLineEdit) and isinstance(
                        widget.parentWidget(), QAbstractSpinBox
                    ):
                        continue
                    label = getattr(widget, "text", lambda: "")()
                    description = (
                        f"{type(widget).__name__} objectName={widget.objectName()!r} "
                        f"text={label!r}"
                    )
                    with self.subTest(control=description):
                        self.assertTrue(widget.accessibleName().strip(), description)
                        self.assertNotEqual(
                            widget.focusPolicy(), Qt.FocusPolicy.NoFocus, description
                        )

                custom_controls = (
                    win._drop,
                    win._player,
                    win._player.canvas,
                    win._player._scrubber,
                    win._player._segment_settings,
                )
                for widget in custom_controls:
                    description = f"{type(widget).__name__} objectName={widget.objectName()!r}"
                    with self.subTest(control=description):
                        self.assertTrue(widget.accessibleName().strip(), description)
                        self.assertNotEqual(
                            widget.focusPolicy(), Qt.FocusPolicy.NoFocus, description
                        )
            finally:
                win._ctl.batch_manifest = None
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
