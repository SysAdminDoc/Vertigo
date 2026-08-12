"""Optional person/object boxes for the Smart Track face fallback.

The default Vertigo path remains face-only.  This module is constructed only
when the user enables the fallback toggle and deliberately avoids downloading
model weights: OpenCV's built-in HOG people detector handles person-shaped
subjects, while a small motion-contour detector provides a useful object
fallback for gameplay, products, and other moving subjects.
"""

from __future__ import annotations

from typing import TypeAlias

import cv2
import numpy as np


DetectionBox: TypeAlias = tuple[float, float, float, float, float]


def is_available() -> bool:
    """Return whether the optional built-in HOG person detector is exposed."""
    try:
        return all(
            hasattr(cv2, name)
            for name in ("HOGDescriptor", "HOGDescriptor_getDefaultPeopleDetector")
        )
    except Exception:
        return False


class ObjectFallbackDetector:
    """Find people or moving objects without an external model download."""

    def __init__(self, *, max_dimension: int = 960) -> None:
        self._max_dimension = max(320, int(max_dimension))
        self._hog: cv2.HOGDescriptor | None = self._build_hog()
        self._previous_gray: np.ndarray | None = None

    def detect(self, frame: np.ndarray, width: int, height: int) -> list[DetectionBox]:
        """Return candidate boxes in source-frame pixel coordinates.

        Person detection wins when it finds a subject.  Motion is evaluated
        otherwise and is intentionally conservative so a static background
        does not become a false target.  Any OpenCV failure is treated as an
        unavailable optional feature and returns an empty list.
        """
        if width <= 0 or height <= 0 or frame is None:
            return []

        try:
            person_boxes = self._person_boxes(frame, width, height)
            gray = self._gray_frame(frame)
            if person_boxes:
                self._previous_gray = gray
                return person_boxes
            motion_boxes = self._motion_boxes(gray, width, height)
            self._previous_gray = gray
            return motion_boxes
        except Exception:
            # Optional tracking must never make Smart Track fail.  Keeping
            # the latest frame still lets the next call recover cleanly.
            try:
                self._previous_gray = self._gray_frame(frame)
            except Exception:
                self._previous_gray = None
            return []

    def close(self) -> None:
        self._hog = None
        self._previous_gray = None

    # ------------------------------------------------------------------ HOG
    def _build_hog(self) -> cv2.HOGDescriptor | None:
        if not is_available():
            return None
        try:
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            return hog
        except Exception:
            return None

    def _person_boxes(self, frame: np.ndarray, width: int, height: int) -> list[DetectionBox]:
        if self._hog is None:
            return []
        scaled, scale = self._scaled_frame(frame, width, height)
        boxes, weights = self._hog.detectMultiScale(
            scaled,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        out: list[DetectionBox] = []
        for index, (x, y, box_width, box_height) in enumerate(boxes):
            score = self._weight_score(weights, index)
            out.append(
                (
                    float(x / scale),
                    float(y / scale),
                    float(box_width / scale),
                    float(box_height / scale),
                    score,
                )
            )
        return out

    @staticmethod
    def _weight_score(weights, index: int) -> float:
        try:
            raw = float(np.asarray(weights[index]).reshape(-1)[0])
        except (IndexError, TypeError, ValueError):
            return 0.55
        # HOG's raw margin is not a probability.  Keep it in the confidence
        # range expected by FaceObservation without pretending it is one.
        return float(max(0.35, min(0.95, 0.55 + raw * 0.1)))

    # -------------------------------------------------------------- movement
    def _motion_boxes(
        self,
        gray: np.ndarray,
        width: int,
        height: int,
    ) -> list[DetectionBox]:
        previous = self._previous_gray
        if previous is None or previous.shape != gray.shape:
            return []

        diff = cv2.absdiff(previous, gray)
        _threshold, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        kernel = np.ones((5, 5), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=2)
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]

        small_height, small_width = gray.shape[:2]
        frame_area = float(small_width * small_height)
        min_area = max(256.0, frame_area * 0.003)
        out: list[DetectionBox] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < min_area:
                continue
            x, y, box_width, box_height = cv2.boundingRect(contour)
            box_area = float(box_width * box_height)
            if box_area > frame_area * 0.85:
                continue
            confidence = max(0.25, min(0.65, 0.25 + area / frame_area * 2.0))
            out.append(
                (
                    float(x * width / small_width),
                    float(y * height / small_height),
                    float(box_width * width / small_width),
                    float(box_height * height / small_height),
                    float(confidence),
                )
            )

        out.sort(key=lambda box: box[2] * box[3], reverse=True)
        return out[:4]

    def _gray_frame(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _scaled, scale = self._scaled_frame(gray, frame.shape[1], frame.shape[0])
        if scale == 1.0:
            return gray
        return _scaled

    def _scaled_frame(
        self,
        frame: np.ndarray,
        width: int,
        height: int,
    ) -> tuple[np.ndarray, float]:
        scale = min(1.0, self._max_dimension / max(width, height))
        if scale >= 0.999:
            return frame, 1.0
        scaled_width = max(1, int(round(width * scale)))
        scaled_height = max(1, int(round(height * scale)))
        return cv2.resize(frame, (scaled_width, scaled_height)), scale
