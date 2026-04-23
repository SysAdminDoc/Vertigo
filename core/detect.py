"""Face/subject detection — lazy MediaPipe, sampled across timeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class TrackPoint:
    """Normalized (0..1) horizontal subject position at time t seconds."""
    t: float
    x: float  # center x in 0..1
    confidence: float


class FaceTracker:
    """Samples the video, runs MediaPipe face detection per frame,
    returns a smoothed track of horizontal subject positions over time.

    Falls back to Haar cascade if MediaPipe is unavailable.
    """

    def __init__(self, sample_fps: float = 2.0, smoothing: float = 0.6) -> None:
        self.sample_fps = max(0.25, sample_fps)
        self.smoothing = min(max(smoothing, 0.0), 0.95)
        self._mp_detector = None
        self._haar = None

    def track(
        self,
        video_path: str | Path,
        progress_cb=None,
        cancel_cb=None,
    ) -> list[TrackPoint]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total_frames / src_fps if src_fps else 0.0
        step_frames = max(1, int(round(src_fps / self.sample_fps)))

        points: list[TrackPoint] = []
        last_x: float | None = None
        frame_idx = 0

        try:
            while True:
                if cancel_cb and cancel_cb():
                    break
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    break

                h, w = frame.shape[:2]
                x_norm, conf = self._detect_center(frame, w, h)
                t = frame_idx / src_fps if src_fps else 0.0

                if x_norm is None:
                    x_norm = last_x if last_x is not None else 0.5
                    conf = 0.1

                if last_x is not None:
                    x_norm = self.smoothing * last_x + (1 - self.smoothing) * x_norm
                last_x = x_norm

                points.append(TrackPoint(t=t, x=float(x_norm), confidence=float(conf)))

                if progress_cb and duration:
                    progress_cb(min(1.0, t / duration))

                frame_idx += step_frames
                if total_frames and frame_idx >= total_frames:
                    break
        finally:
            cap.release()

        return points

    def _detect_center(self, frame: np.ndarray, w: int, h: int) -> tuple[float | None, float]:
        """Return (normalized_x_center, confidence) of the dominant subject, or (None, 0)."""
        boxes = self._mediapipe_boxes(frame, w, h)
        if not boxes:
            boxes = self._haar_boxes(frame, w, h)
        if not boxes:
            return None, 0.0

        # Pick largest box (closest subject).
        bx, by, bw, bh, conf = max(boxes, key=lambda b: b[2] * b[3])
        cx = (bx + bw / 2) / w
        return float(cx), float(conf)

    def _mediapipe_boxes(self, frame: np.ndarray, w: int, h: int):
        try:
            if self._mp_detector is None:
                import mediapipe as mp
                self._mp_detector = mp.solutions.face_detection.FaceDetection(
                    model_selection=1,
                    min_detection_confidence=0.5,
                )
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._mp_detector.process(rgb)
        except Exception:
            self._mp_detector = False  # sentinel: disabled
            return []
        if not result or not result.detections:
            return []
        out = []
        for det in result.detections:
            box = det.location_data.relative_bounding_box
            bx = max(0.0, box.xmin) * w
            by = max(0.0, box.ymin) * h
            bw = box.width * w
            bh = box.height * h
            out.append((bx, by, bw, bh, det.score[0] if det.score else 0.5))
        return out

    def _haar_boxes(self, frame: np.ndarray, w: int, h: int):
        try:
            if self._haar is None:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self._haar = cv2.CascadeClassifier(cascade_path)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._haar.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4)
        except Exception:
            return []
        return [(float(x), float(y), float(bw), float(bh), 0.5) for (x, y, bw, bh) in faces]

    def close(self) -> None:
        if self._mp_detector and self._mp_detector is not False:
            try:
                self._mp_detector.close()
            except Exception:
                pass
            self._mp_detector = None
