"""Main-window smoke test — a regression net for the controller split.

The test pre-dates the ui/main_window.py → main_window + main_controller
decomposition. It constructs MainWindow with no clip, drives the paths
the controller touches (queue add/select, mode change, preset change,
theme change), and asserts that nothing raises. Probe errors from the
fake clip path are expected and must be absorbed by the window rather
than propagated out of the signal handlers.

Scope: construction + pure UI-state signal flow. It deliberately avoids
starting workers (detect/encode/subtitle), which would need real media
and a full ffmpeg pipeline.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        # Zero-out animations so the fade on tab switches and toast fades
        # don't leak live timers into other tests running in the same proc.
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)
        # Prime the theme so MainWindow sees a valid stylesheet / palette.
        from ui.theme import apply_app_theme
        apply_app_theme(cls._app, "mocha")

    def test_constructs_clean_and_exercises_core_signals(self) -> None:
        from core.presets import PRESETS
        from core.reframe import ReframeMode
        from ui.main_window import MainWindow

        # A temp path is enough to append a QueueEntry — probe will fail
        # on the empty file and the window is expected to toast + skip.
        with tempfile.TemporaryDirectory() as tmp:
            fake_clip = Path(tmp) / "fake.mp4"
            fake_clip.write_bytes(b"")

            win = MainWindow()
            try:
                # queue add + select -> exercises probe() error path
                entry = win._queue.add(fake_clip)
                self.assertGreaterEqual(win._queue.count(), 1)
                win._queue.select(entry.id)

                # mode change — every mode should apply without raising
                for mode in ReframeMode:
                    win._on_mode_changed(mode)

                # preset swap — cycle through every declared preset id
                for pid in PRESETS:
                    win._choose_preset(pid)

                # theme switch — must not raise for any palette
                for theme_id in ("mocha", "graphite", "latte"):
                    win._apply_theme(theme_id, persist=False)

                # clear directly — win._clear_queue() would pop a modal
                # QMessageBox, which hangs offscreen tests. Exercise the
                # underlying queue API + the active-clip reset helper
                # that the signal handler calls on confirmation.
                win._queue.clear()
                win._clear_active_clip()
                self.assertEqual(win._queue.count(), 0)
            finally:
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
