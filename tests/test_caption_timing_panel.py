"""Offscreen smoke coverage for the caption review controls."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


class CaptionTimingPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication(sys.argv)
        from ui.theme import apply_app_theme

        apply_app_theme(cls._app, "mocha")

    def test_review_controls_edit_preview_and_save(self) -> None:
        from core.caption_types import Caption
        from ui.subtitles_panel import SubtitlesPanel

        panel = SubtitlesPanel()
        panel.set_clip_loaded(True)
        panel.set_srt_path(Path("captions.vertigo.srt"))
        panel.set_captions(
            [
                Caption(0.0, 2.0, "first chunk"),
                Caption(2.2, 4.0, "second chunk"),
            ]
        )
        try:
            self.assertEqual(panel._review_list.count(), 2)
            panel.preview_at(2.5)
            self.assertEqual(panel._review_list.currentRow(), 1)

            panel._nudge_amount.setValue(0.25)
            panel.nudge_selected()
            self.assertEqual(panel.captions()[1].start, 2.45)
            self.assertTrue(panel._review_dirty)

            saved: list[list[Caption]] = []
            panel.save_caption_edits_requested.connect(lambda captions: saved.append(captions))
            panel.save_caption_edits()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0][1].start, 2.45)

            panel.mark_caption_edits_saved()
            self.assertFalse(panel._review_dirty)
        finally:
            panel.close()
            panel.deleteLater()

    def test_controller_persists_the_sidecar_used_by_export(self) -> None:
        from core.caption_types import Caption
        from ui.batch_queue import QueueEntry
        from ui.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "clip.vertigo.srt"
            sidecar.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nold timing\n",
                encoding="utf-8",
            )
            win = MainWindow()
            try:
                entry = QueueEntry(Path(tmp) / "clip.mp4")
                win._current_entry = entry
                win._ctl.clip_subs[entry.id] = sidecar
                win._subs_panel.set_clip_loaded(True)
                win._subs_panel.set_srt_path(sidecar)
                captions = [Caption(1.5, 3.5, "adjusted timing")]

                win._ctl.save_caption_edits(captions)

                self.assertEqual(win._ctl.clip_subs[entry.id], sidecar)
                self.assertEqual(win._ctl.clip_captions[entry.id], captions)
                self.assertIn(
                    "00:00:01,500 --> 00:00:03,500",
                    sidecar.read_text(encoding="utf-8"),
                )
                self.assertFalse(win._subs_panel._review_dirty)
            finally:
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
