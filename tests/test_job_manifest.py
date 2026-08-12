"""Resumable batch-manifest persistence and cleanup coverage."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class JobManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_manifest_round_trips_recipe_progress_and_part_path(self) -> None:
        from core.job_manifest import BatchManifest, ManifestEntry, load, save

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports"
            manifest_path = Path(tmp) / "batch-manifest.json"
            entry = ManifestEntry(
                source_path=Path(tmp) / "clip.mp4",
                output_path=root / "clip_shorts.mp4",
                temp_output_path=root / ".vertigo-abc-clip_shorts.part.mp4",
                status="active",
                message="encoding…",
            )
            original = BatchManifest.new(
                output_dir=root,
                preset_id="shorts",
                mode="smart_track",
                trim_low=1.25,
                trim_high=42.5,
                options={"quality": 82, "overlays": [{"text": "Hook"}]},
                entries=[entry],
            )

            save(original, manifest_path)
            loaded = load(manifest_path)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertTrue(loaded.incomplete)
            self.assertEqual(loaded.preset_id, "shorts")
            self.assertEqual(loaded.mode, "smart_track")
            self.assertEqual((loaded.trim_low, loaded.trim_high), (1.25, 42.5))
            self.assertEqual(loaded.options["quality"], 82)
            self.assertEqual(loaded.entries[0].temp_output_path, entry.temp_output_path)
            self.assertFalse(manifest_path.with_suffix(".json.tmp").exists())

    def test_cleanup_removes_only_hidden_parts_inside_output_dir(self) -> None:
        from core.job_manifest import BatchManifest, ManifestEntry, cleanup_partial_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports"
            root.mkdir()
            outside = Path(tmp) / ".vertigo-abc-outside.part.mp4"

            manifest = BatchManifest.new(
                output_dir=root,
                preset_id="shorts",
                mode="center",
                trim_low=0.0,
                trim_high=0.0,
                options={},
                entries=[
                    ManifestEntry(
                        source_path=Path(tmp) / "clip.mp4",
                        status="active",
                    )
                ],
            )
            part = root / f".vertigo-{manifest.batch_id}-clip.part.mp4"
            discovered_part = root / f".vertigo-{manifest.batch_id}-clip.pycaps.part.mp4"
            part.write_bytes(b"partial")
            discovered_part.write_bytes(b"partial")
            outside.write_bytes(b"partial")
            manifest.entries[0].temp_output_path = part
            removed = cleanup_partial_outputs(manifest)

            self.assertFalse(part.exists())
            self.assertFalse(discovered_part.exists())
            self.assertTrue(outside.exists(), "cleanup must not escape the output directory")
            self.assertEqual(len(removed), 2)

    def test_completed_manifest_is_not_offered_for_resume(self) -> None:
        from core.job_manifest import BatchManifest, ManifestEntry

        manifest = BatchManifest.new(
            output_dir=Path("exports"),
            preset_id="reels",
            mode="center",
            trim_low=0.0,
            trim_high=0.0,
            options={},
            entries=[ManifestEntry(source_path=Path("clip.mp4"), status="done")],
        )
        manifest.state = "complete"
        self.assertFalse(manifest.incomplete)
        self.assertEqual(manifest.pending_entries, [])

    def test_starting_batch_publishes_manifest_before_driver_runs(self) -> None:
        from core.job_manifest import discard, load
        from ui.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "exports"
            manifest_file = Path(tmp) / "batch.json"
            source = Path(tmp) / "clip.mp4"
            source.write_bytes(b"not a real clip")
            with patch.dict(os.environ, {"VERTIGO_BATCH_MANIFEST": str(manifest_file)}):
                win = MainWindow()
                try:
                    win._queue.add(source)
                    with patch(
                        "ui.file_dialogs.get_existing_directory",
                        return_value=root,
                    ), patch.object(
                        win._ctl,
                        "_confirm_batch_platform_durations",
                        return_value=True,
                    ), patch.object(win._ctl, "_advance_batch"):
                        win._ctl.start_batch_export()

                    manifest = load(manifest_file)
                    self.assertIsNotNone(manifest)
                    assert manifest is not None
                    self.assertTrue(manifest.incomplete)
                    self.assertEqual(manifest.preset_id, win._preset.id)
                    self.assertEqual(manifest.mode, win._mode.value)
                    self.assertEqual(manifest.entries[0].source_path, source)
                    self.assertTrue(
                        manifest.entries[0].temp_output_path.name.startswith(".vertigo-")
                    )
                finally:
                    win.close()
                    win.deleteLater()
                    discard(manifest_file)


if __name__ == "__main__":
    unittest.main()
