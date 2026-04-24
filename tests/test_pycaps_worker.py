"""Regression tests for the pycaps post-encode worker.

The pycaps animated-caption pass is a full video re-encode that takes
minutes on long clips. Earlier code called it synchronously from the
encode-done slot (``_apply_pycaps_pass``), freezing the entire GUI for
the duration of the composite. This test pins the replacement: the
pass now runs on ``PycapsWorker``, the export finalises through
``_on_pycaps_done`` / ``_on_pycaps_failed``, and cancellation + missing
dep + no-transcript paths all fall back to the reframed export cleanly.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


class PycapsWorkerContractTests(unittest.TestCase):
    """PycapsWorker itself — no Qt event loop needed for these; we call
    ``run()`` directly on the test thread."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_cancel_before_run_emits_cancelled(self) -> None:
        from workers.pycaps_worker import PycapsWorker

        ok: list[str] = []
        failed: list[str] = []
        worker = PycapsWorker(
            Path("/tmp/source.mp4"),
            Path("/tmp/out.mp4"),
            captions=[],
            template="hype",
        )
        worker.finished_ok.connect(ok.append)
        worker.failed.connect(failed.append)
        worker.cancel()
        worker.run()

        self.assertEqual(ok, [])
        self.assertEqual(failed, ["Cancelled."])

    def test_render_failure_propagates_as_failed(self) -> None:
        """If pycaps isn't installed, render_composited raises RuntimeError
        and the worker must translate that into a ``failed`` signal —
        never a spurious ``finished_ok``."""
        from core import animated_captions
        if animated_captions.is_available():
            self.skipTest("pycaps installed; raise path not reachable")

        from workers.pycaps_worker import PycapsWorker
        ok: list[str] = []
        failed: list[str] = []
        worker = PycapsWorker(
            Path("/tmp/source.mp4"),
            Path("/tmp/out.mp4"),
            captions=[],
            template="hype",
        )
        worker.finished_ok.connect(ok.append)
        worker.failed.connect(failed.append)
        worker.run()

        self.assertEqual(ok, [])
        self.assertTrue(failed)
        self.assertNotEqual(failed[0], "Cancelled.")


class ControllerPycapsBranchTests(unittest.TestCase):
    """``MainController._on_export_done`` must branch to the async
    worker when animated captions are selected, and fall through to
    direct finalisation otherwise. Spins up a real MainWindow (same
    pattern as ``test_main_window_smoke``) so the controller sees the
    widgets its finalisation path touches.
    """

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)
        from ui.theme import apply_app_theme
        apply_app_theme(cls._app, "mocha")

    def _build_window(self):
        from ui.main_window import MainWindow
        return MainWindow()

    def test_no_animated_style_finalises_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.mp4"
            out_path.write_bytes(b"")

            win = self._build_window()
            try:
                ctl = win._ctl
                ctl._on_export_done(str(out_path), entry_id=None)

                self.assertIsNone(ctl.pycaps_worker)
                self.assertIsNone(ctl._pending_pycaps)
                self.assertEqual(win._export_progress.value(), 100)
                self.assertEqual(ctl.last_output_path, out_path)
            finally:
                win.close()
                win.deleteLater()

    def test_animated_style_without_transcript_falls_through(self) -> None:
        """User selected an animated style but never ran transcription.
        Controller logs a warning and finalises without kicking the
        worker — the user still gets a reframed export."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.mp4"
            out_path.write_bytes(b"")

            win = self._build_window()
            try:
                ctl = win._ctl
                ctl.animated_styles[7] = "hype"
                # clip_captions[7] is intentionally absent.
                ctl._on_export_done(str(out_path), entry_id=7)

                self.assertIsNone(ctl.pycaps_worker)
                self.assertIsNone(ctl._pending_pycaps)
                self.assertEqual(win._export_progress.value(), 100)
            finally:
                win.close()
                win.deleteLater()

    def test_pycaps_failed_falls_back_to_reframed_export(self) -> None:
        """If the pycaps worker emits failed(), the controller must
        delete the partial tmp output, keep the reframed file, and
        still finalise the export (no half-finished state)."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.mp4"
            out_path.write_bytes(b"reframed")
            tmp_out = out_path.with_name(f"{out_path.stem}.pycaps{out_path.suffix}")
            tmp_out.write_bytes(b"partial")

            win = self._build_window()
            try:
                ctl = win._ctl
                ctl._pending_pycaps = {
                    "reframed_out": out_path,
                    "tmp_out": tmp_out,
                    "entry_id": None,
                    "template": "hype",
                }
                ctl._on_pycaps_failed("RuntimeError: boom")

                self.assertFalse(tmp_out.exists(), "partial pycaps output must be removed")
                self.assertTrue(out_path.exists(), "reframed export must be preserved")
                self.assertEqual(ctl.last_output_path, out_path)
                self.assertIsNone(ctl._pending_pycaps)
            finally:
                win.close()
                win.deleteLater()

    def test_pycaps_cancel_stays_quiet(self) -> None:
        """A user-triggered cancel must still finalise (unlock the UI)
        without leaving pending pycaps state behind."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.mp4"
            out_path.write_bytes(b"reframed")
            tmp_out = out_path.with_name(f"{out_path.stem}.pycaps{out_path.suffix}")

            win = self._build_window()
            try:
                ctl = win._ctl
                ctl._pending_pycaps = {
                    "reframed_out": out_path,
                    "tmp_out": tmp_out,
                    "entry_id": None,
                    "template": "hype",
                }
                ctl._on_pycaps_failed("Cancelled.")

                self.assertEqual(ctl.last_output_path, out_path)
                self.assertIsNone(ctl._pending_pycaps)
            finally:
                win.close()
                win.deleteLater()

    def test_pycaps_done_swaps_file_into_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.mp4"
            out_path.write_bytes(b"reframed")
            tmp_out = out_path.with_name(f"{out_path.stem}.pycaps{out_path.suffix}")
            tmp_out.write_bytes(b"animated")

            win = self._build_window()
            try:
                ctl = win._ctl
                ctl._pending_pycaps = {
                    "reframed_out": out_path,
                    "tmp_out": tmp_out,
                    "entry_id": None,
                    "template": "hype",
                }
                ctl._on_pycaps_done(str(tmp_out))

                self.assertTrue(out_path.exists())
                self.assertFalse(tmp_out.exists())
                self.assertEqual(out_path.read_bytes(), b"animated")
                self.assertEqual(ctl.last_output_path, out_path)
            finally:
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
