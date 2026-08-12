"""Opt-in person/object fallback coverage."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

import numpy as np


class ObjectFallbackTests(unittest.TestCase):
    def test_detector_reports_availability_and_follows_motion(self) -> None:
        from core.object_tracking import ObjectFallbackDetector, is_available

        self.assertIsInstance(is_available(), bool)
        detector = ObjectFallbackDetector(max_dimension=320)
        detector._hog = None
        try:
            first = np.zeros((120, 200, 3), dtype=np.uint8)
            second = first.copy()
            second[40:90, 120:170] = 255
            self.assertEqual(detector.detect(first, 200, 120), [])
            boxes = detector.detect(second, 200, 120)
        finally:
            detector.close()

        self.assertTrue(boxes)
        x, _y, width, _height, confidence = boxes[0]
        self.assertGreater(x + width / 2, 100.0)
        self.assertGreater(confidence, 0.0)

    def test_face_tracker_keeps_fallback_out_of_default_path(self) -> None:
        from core.detect import FaceTracker

        with patch.object(FaceTracker, "_new_object_detector", return_value=None) as factory:
            default_tracker = FaceTracker()
            try:
                factory.assert_not_called()
            finally:
                default_tracker.close()

            opt_in_tracker = FaceTracker(use_object_fallback=True)
            try:
                factory.assert_called_once()
            finally:
                opt_in_tracker.close()

    def test_object_boxes_are_only_used_after_face_boxes_are_empty(self) -> None:
        from core.detect import FaceTracker

        class StubDetector:
            def __init__(self) -> None:
                self.calls = 0

            def detect(self, frame, width, height):
                self.calls += 1
                return [(80.0, 20.0, 40.0, 60.0, 0.4)]

            def close(self) -> None:
                pass

        tracker = FaceTracker()
        stub = StubDetector()
        tracker._object_detector = stub
        frame = np.zeros((100, 160, 3), dtype=np.uint8)
        try:
            with patch.object(tracker, "_mediapipe_boxes", return_value=[]), patch.object(
                tracker, "_haar_boxes", return_value=[]
            ):
                self.assertEqual(
                    tracker._detect_boxes(
                        frame, 160, 100, use_object_fallback=False
                    ),
                    [],
                )
                self.assertEqual(stub.calls, 0)
                boxes = tracker._detect_boxes(
                    frame, 160, 100, use_object_fallback=True
                )
                self.assertEqual(len(boxes), 1)
                self.assertEqual(stub.calls, 1)

            with patch.object(
                tracker,
                "_mediapipe_boxes",
                return_value=[(10.0, 10.0, 20.0, 20.0, 0.9)],
            ), patch.object(tracker, "_haar_boxes", return_value=[]):
                face_boxes = tracker._detect_boxes(
                    frame, 160, 100, use_object_fallback=True
                )
            self.assertEqual(face_boxes, [(10.0, 10.0, 20.0, 20.0, 0.9)])
            self.assertEqual(stub.calls, 1)
        finally:
            tracker.close()

    def test_worker_passes_opt_in_flag_without_downloading_weights(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        _app = QApplication.instance() or QApplication(sys.argv)
        from workers.detect_worker import DetectWorker

        captured: dict[str, object] = {}

        class FakeTracker:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

            def track_with_cameraman(self, *args, **kwargs):
                captured["call"] = kwargs
                return []

            def close(self) -> None:
                pass

        with patch("workers.detect_worker.FaceTracker", FakeTracker):
            worker = DetectWorker(
                "/tmp/clip.mp4",
                crop_width_frac=0.5,
                use_object_fallback=True,
            )
            worker.run()

        self.assertTrue(captured["use_object_fallback"])
        self.assertTrue(captured["call"]["use_cluster_filter"])


if __name__ == "__main__":
    unittest.main()
