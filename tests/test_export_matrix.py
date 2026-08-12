"""Matrix child progress stays grouped under one source queue entry."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ExportMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_child_successes_are_grouped_until_all_platforms_finish(self) -> None:
        from core.presets import PRESETS
        from ui.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "clip.mp4"
            source.write_bytes(b"source")
            manifest_file = root / "matrix.json"
            win = MainWindow()
            try:
                with patch.dict(os.environ, {"VERTIGO_BATCH_MANIFEST": str(manifest_file)}):
                    entry = win._queue.add(source)
                    ctl = win._ctl
                    ctl.batch_out_dir = root / "exports"
                    ctl.batch_out_dir.mkdir()
                    ctl._new_batch_manifest(
                        [entry], matrix_preset_ids=["shorts", "tiktok"]
                    )
                    ctl.batch_running = True
                    ctl._active_batch_entry_id = entry.id

                    first_final, first_part = ctl._batch_output_paths(entry, "shorts")
                    first_part.write_bytes(b"shorts")
                    ctl._batch_final_outputs[entry.id] = first_final
                    win._choose_preset("shorts")
                    with patch.object(ctl, "_advance_batch"):
                        ctl._finish_export_done(first_part, entry.id)

                    self.assertEqual(entry.status.value, "active")
                    self.assertEqual(
                        ctl._batch_manifest_entries[entry.id].children["shorts"]["status"],
                        "done",
                    )
                    self.assertTrue(first_final.exists())

                    second_final, second_part = ctl._batch_output_paths(entry, "tiktok")
                    second_part.write_bytes(b"tiktok")
                    ctl._batch_final_outputs[entry.id] = second_final
                    win._choose_preset("tiktok")
                    with patch.object(ctl, "_advance_batch"):
                        ctl._finish_export_done(second_part, entry.id)

                    self.assertEqual(entry.status.value, "done")
                    self.assertEqual(
                        ctl._batch_manifest_entries[entry.id].children["tiktok"]["status"],
                        "done",
                    )
                    self.assertTrue(second_final.exists())
                    self.assertEqual(win._preset, PRESETS["tiktok"])
            finally:
                win._ctl.batch_manifest = None
                win.close()
                win.deleteLater()
                from core.job_manifest import discard

                with patch.dict(os.environ, {"VERTIGO_BATCH_MANIFEST": str(manifest_file)}):
                    discard(manifest_file)

    def test_one_failed_platform_does_not_hide_other_children(self) -> None:
        from ui.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "clip.mp4"
            source.write_bytes(b"source")
            manifest_file = root / "matrix-failure.json"
            win = MainWindow()
            try:
                with patch.dict(os.environ, {"VERTIGO_BATCH_MANIFEST": str(manifest_file)}):
                    entry = win._queue.add(source)
                    ctl = win._ctl
                    ctl.batch_out_dir = root / "exports"
                    ctl.batch_out_dir.mkdir()
                    ctl._new_batch_manifest(
                        [entry], matrix_preset_ids=["shorts", "tiktok"]
                    )
                    ctl.batch_running = True
                    ctl._active_batch_entry_id = entry.id
                    win._choose_preset("shorts")

                    with patch.object(ctl, "_advance_batch"):
                        ctl._on_export_fail("encoder failed", entry.id)

                    self.assertEqual(entry.status.value, "active")
                    children = ctl._batch_manifest_entries[entry.id].children
                    self.assertEqual(children["shorts"]["status"], "failed")
                    self.assertEqual(children["tiktok"]["status"], "pending")
            finally:
                win._ctl.batch_manifest = None
                win.close()
                win.deleteLater()
                from core.job_manifest import discard

                with patch.dict(os.environ, {"VERTIGO_BATCH_MANIFEST": str(manifest_file)}):
                    discard(manifest_file)


if __name__ == "__main__":
    unittest.main()
