"""Regression coverage for worker-owned output cleanup."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class SubtitleOutputScrubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_cancel_removes_new_sidecar_and_tmp_sibling(self) -> None:
        from core.subtitles import TranscribeResult
        from workers.subtitle_worker import SubtitleWorker

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "clip.mp4"
            out_dir = root / "source"
            source.write_bytes(b"")

            worker = SubtitleWorker(source, out_dir)
            failed: list[str] = []
            worker.failed.connect(failed.append)

            def fake_transcribe(*args, **kwargs):
                out_dir.mkdir()
                output = out_dir / "clip.vertigo.srt"
                output.write_text("partial", encoding="utf-8")
                output.with_suffix(output.suffix + ".tmp").write_text(
                    "orphan", encoding="utf-8"
                )
                worker.cancel()
                return TranscribeResult(path=output, captions=[])

            with mock.patch(
                "workers.subtitle_worker.transcribe_and_write",
                side_effect=fake_transcribe,
            ):
                worker.run()

            self.assertEqual(failed, ["Cancelled."])
            self.assertFalse((out_dir / "clip.vertigo.srt").exists())
            self.assertFalse((out_dir / "clip.vertigo.srt.tmp").exists())

    def test_failed_refresh_preserves_existing_sidecar(self) -> None:
        from workers.subtitle_worker import SubtitleWorker

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "clip.mp4"
            out_dir = root / "source"
            output = out_dir / "clip.vertigo.srt"
            source.write_bytes(b"")
            out_dir.mkdir()
            output.write_text("previous captions", encoding="utf-8")

            worker = SubtitleWorker(source, out_dir)
            failed: list[str] = []
            worker.failed.connect(failed.append)

            with mock.patch(
                "workers.subtitle_worker.transcribe_and_write",
                side_effect=RuntimeError("writer failed"),
            ):
                worker.run()

            self.assertTrue(failed)
            self.assertIn("RuntimeError: writer failed", failed[0])
            self.assertEqual(output.read_text(encoding="utf-8"), "previous captions")


class AtomicSubtitleWriterTests(unittest.TestCase):
    def test_writer_removes_temp_when_replace_fails(self) -> None:
        from core.subtitles import write_srt

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "clip.vertigo.srt"
            with mock.patch("core.subtitles.os.replace", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    write_srt([], output)

            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(output.suffix + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
