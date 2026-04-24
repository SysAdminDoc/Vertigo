"""Integration-module smoke tests.

Nine optional-dependency modules under ``core/`` (Tier 1–3 integrations)
expose ``is_available()`` probes plus a well-defined fallback path for
when the heavy dep isn't installed. These tests pin that contract:

  * every module imports cleanly on a bare Vertigo install
  * ``is_available()`` returns a bool (never raises)
  * the documented fallback path works when the heavy dep is missing
  * the public API doesn't crash on empty / missing input

The tests deliberately do NOT download models or call external APIs —
those paths are only exercised when the optional dep is present on the
test machine, at which point the test upgrades from a pure-import
check to a "does it work" check.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


# ---------------------------------------------------------------- vad

class VadSmokeTests(unittest.TestCase):
    def test_module_imports_without_silero(self) -> None:
        from core import vad
        self.assertIsInstance(vad.is_available(), bool)

    def test_detect_speech_raises_when_unavailable(self) -> None:
        from core import vad
        if vad.is_available():
            self.skipTest("silero-vad is installed; availability guard not reachable")
        with self.assertRaises(RuntimeError):
            vad.detect_speech(Path("/tmp/does-not-exist.mp4"))

    def test_plan_tight_trim_handles_empty(self) -> None:
        from core.vad import plan_tight_trim
        self.assertIsNone(plan_tight_trim([], duration=60.0))

    def test_plan_tight_trim_honors_pad_and_bounds(self) -> None:
        from core.vad import SpeechSpan, plan_tight_trim
        spans = [SpeechSpan(2.0, 10.0), SpeechSpan(20.0, 25.0)]
        lo, hi = plan_tight_trim(spans, duration=30.0, pad_sec=0.5)
        # Pad shrinks the left edge by 0.5 but clamps to 0.0; right edge
        # pads to 25.5 which is inside the 30-s clip.
        self.assertAlmostEqual(lo, 1.5, places=3)
        self.assertAlmostEqual(hi, 25.5, places=3)

    def test_speech_coverage_bounds(self) -> None:
        from core.vad import SpeechSpan, speech_coverage
        spans = [SpeechSpan(0.0, 5.0), SpeechSpan(10.0, 20.0)]
        # 15 of 30 = 0.5
        self.assertAlmostEqual(speech_coverage(spans, 30.0), 0.5, places=3)
        self.assertEqual(speech_coverage([], 30.0), 0.0)
        self.assertEqual(speech_coverage(spans, 0.0), 0.0)


# ---------------------------------------------------------------- animated captions

class AnimatedCaptionsSmokeTests(unittest.TestCase):
    def test_module_imports_without_pycaps(self) -> None:
        from core import animated_captions
        self.assertIsInstance(animated_captions.is_available(), bool)

    def test_available_styles_returns_known_set(self) -> None:
        from core.animated_captions import available_styles, DEFAULT_STYLE
        styles = available_styles()
        self.assertIn(DEFAULT_STYLE, styles)
        self.assertTrue(all(isinstance(s, str) for s in styles))

    def test_render_raises_when_unavailable(self) -> None:
        from core import animated_captions
        if animated_captions.is_available():
            self.skipTest("pycaps is installed; availability guard not reachable")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                animated_captions.render(
                    [], Path(tmp), source_video=Path("/tmp/x.mp4"),
                )

    def test_build_overlay_filter_shape(self) -> None:
        from core.animated_captions import build_overlay_filter
        frag = build_overlay_filter(Path("/tmp/anything.mov"))
        self.assertIn("overlay", frag)


# ---------------------------------------------------------------- tracker_boxmot

class TrackerBoxmotSmokeTests(unittest.TestCase):
    def test_make_tracker_falls_back_when_unavailable(self) -> None:
        from core.tracker_boxmot import FallbackTrackerAdapter, make_tracker
        tracker = make_tracker()
        # Either BoxMOT is present (real adapter) or we get the fallback.
        # Both must respond to step() + reset() without raising.
        tracker.reset()
        result = tracker.step(0, [])
        self.assertIsNone(result)
        # Fallback adapter in particular should be returned when boxmot
        # is not importable.
        from core.tracker_boxmot import is_available
        if not is_available():
            self.assertIsInstance(tracker, FallbackTrackerAdapter)

    def test_fallback_matches_speaker_tracker_behavior(self) -> None:
        from core.cameraman import FaceObservation
        from core.tracker_boxmot import FallbackTrackerAdapter
        tr = FallbackTrackerAdapter()
        obs = [FaceObservation(frame=0, t=0.0, cx=500, cy=400, w=60, h=80)]
        active = tr.step(0, obs)
        self.assertIsNotNone(active)
        self.assertAlmostEqual(active.cx, 500.0, places=1)


# ---------------------------------------------------------------- auto_edit

class AutoEditSmokeTests(unittest.TestCase):
    def test_is_available_returns_bool(self) -> None:
        from core import auto_edit
        self.assertIsInstance(auto_edit.is_available(), bool)

    def test_plan_cuts_raises_when_missing(self) -> None:
        from core import auto_edit
        if auto_edit.is_available():
            self.skipTest("auto-editor on PATH; availability guard not reachable")
        with self.assertRaises(RuntimeError):
            auto_edit.plan_cuts(Path("/tmp/does-not-exist.mp4"))

    def test_parse_timeline_handles_empty(self) -> None:
        from core.auto_edit import _parse_timeline
        self.assertEqual(_parse_timeline({}), [])
        self.assertEqual(_parse_timeline({"chunks": []}), [])

    def test_parse_timeline_picks_speed_1(self) -> None:
        from core.auto_edit import _parse_timeline
        data = {
            "timeline_fps": 30.0,
            "chunks": [[0, 60, 1.0], [60, 90, 99999], [90, 150, 1.0]],
        }
        spans = _parse_timeline(data)
        self.assertEqual(len(spans), 2)
        self.assertAlmostEqual(spans[0].start, 0.0)
        self.assertAlmostEqual(spans[0].end, 2.0)  # 60f / 30fps
        self.assertAlmostEqual(spans[1].start, 3.0)
        self.assertAlmostEqual(spans[1].end, 5.0)


# ---------------------------------------------------------------- highlights

class HighlightsSmokeTests(unittest.TestCase):
    def test_is_available_returns_bool(self) -> None:
        from core import highlights
        self.assertIsInstance(highlights.is_available(), bool)

    def test_fallback_does_not_raise_on_bad_path(self) -> None:
        from core.highlights import score_spans
        # No file → probe() raises, but the function should catch and
        # return an empty list so UI rendering doesn't explode.
        result = score_spans(Path("/tmp/does-not-exist.mp4"))
        self.assertEqual(result, [])


# ---------------------------------------------------------------- cluster_track

class ClusterTrackSmokeTests(unittest.TestCase):
    def test_cluster_filter_is_identity_for_persistent_faces(self) -> None:
        """A single face in every frame should pass the persistence
        filter unchanged."""
        from core.cameraman import FaceObservation
        from core.cluster_track import cluster_filter

        # 10 frames, same face at cx=500
        frames = [
            [FaceObservation(frame=i, t=i * 0.1, cx=500.0, cy=400.0, w=60.0, h=80.0)]
            for i in range(10)
        ]
        out = cluster_filter(frames, source_width=1920, min_persistence=3, temporal_window=3)
        self.assertEqual(len(out), 10)
        self.assertTrue(all(len(f) == 1 for f in out))

    def test_face_tracker_imports_tracker_factory(self) -> None:
        """Smart Track must pick up core.tracker_boxmot.make_tracker
        so installing the optional `boxmot` dep flips the behaviour
        automatically. We can't exercise the real tracker here without
        a clip, but we can pin the module-level import contract so a
        future refactor that removes it has a red test to show for it.
        """
        import core.detect as detect
        from core.tracker_boxmot import make_tracker
        self.assertIs(detect.make_tracker, make_tracker)

    def test_face_tracker_accepts_use_cluster_filter_kwarg(self) -> None:
        """The kwarg added in the wiring pass must reach
        ``track_with_cameraman`` and the cluster_filter import must
        succeed without triggering detection on a real clip."""
        from core.detect import FaceTracker
        tracker = FaceTracker()
        try:
            # The kwarg must be accepted (keyword-only). A bad clip path
            # returns [] — we only need the call not to raise on the
            # signature.
            points = tracker.track_with_cameraman(
                "/tmp/does-not-exist.mp4",
                crop_width_frac=0.5,
                use_cluster_filter=True,
            )
            self.assertEqual(points, [])
        finally:
            tracker.close()

    def test_cluster_filter_drops_single_frame_noise(self) -> None:
        """A face that appears once and disappears should be filtered."""
        from core.cameraman import FaceObservation
        from core.cluster_track import cluster_filter

        frames = []
        for i in range(10):
            obs = [FaceObservation(frame=i, t=i * 0.1, cx=500.0, cy=400.0, w=60.0, h=80.0)]
            if i == 5:
                # Add a one-frame noise detection at a very different cx
                obs.append(FaceObservation(frame=i, t=i * 0.1, cx=1200.0, cy=400.0, w=40.0, h=40.0))
            frames.append(obs)

        out = cluster_filter(
            frames,
            source_width=1920,
            spatial_tol_frac=0.05,  # tighter tolerance
            min_persistence=3,
            temporal_window=2,
        )
        # Frame 5 used to have 2 observations; the noise one should be dropped.
        self.assertEqual(len(out[5]), 1)
        self.assertAlmostEqual(out[5][0].cx, 500.0)


# ---------------------------------------------------------------- diarize

class DiarizeSmokeTests(unittest.TestCase):
    def test_is_available_returns_bool(self) -> None:
        from core import diarize
        self.assertIsInstance(diarize.is_available(), bool)

    def test_has_hf_token_bool(self) -> None:
        from core.diarize import has_hf_token
        self.assertIsInstance(has_hf_token(), bool)

    def test_align_to_faces_empty(self) -> None:
        from core.diarize import align_to_faces
        self.assertEqual(align_to_faces([], []), {})

    def test_diarize_raises_clear_error_on_missing_dep(self) -> None:
        from core import diarize
        if diarize.is_available():
            self.skipTest("pyannote.audio installed; guard not reachable")
        with self.assertRaises(RuntimeError):
            diarize.diarize(Path("/tmp/nope.wav"))


# ---------------------------------------------------------------- broll

class BrollSmokeTests(unittest.TestCase):
    def test_keywords_fallback_runs_without_keybert(self) -> None:
        from core.broll import _keywords_fallback
        hits = _keywords_fallback("the quick brown fox jumps over the lazy dog", top_n=2)
        self.assertGreaterEqual(len(hits), 1)
        # Stop-words ("the", "over") should not win.
        words = [h[0] for h in hits]
        self.assertNotIn("the", words)

    def test_search_pexels_without_key_returns_empty(self) -> None:
        from core.broll import search_pexels
        # Explicitly wipe the env so the early-exit branch runs.
        prev = os.environ.pop("PEXELS_API_KEY", None)
        try:
            self.assertEqual(search_pexels("mountain"), [])
        finally:
            if prev is not None:
                os.environ["PEXELS_API_KEY"] = prev

    def test_plan_broll_inserts_graceful_when_no_keywords(self) -> None:
        from core.broll import plan_broll_inserts
        self.assertEqual(plan_broll_inserts([], clip_duration_sec=30.0), [])

    def test_rank_candidates_falls_back_to_native_ranking(self) -> None:
        from core.broll import StockCandidate, rank_candidates
        candidates = [
            StockCandidate(url="a", preview_url="", duration_sec=5, width=1280, height=720,
                           keyword="k", native_score=0.8),
            StockCandidate(url="b", preview_url="", duration_sec=5, width=1280, height=720,
                           keyword="k", native_score=0.2),
        ]
        picked = rank_candidates("k", candidates, top_k=1)
        self.assertEqual(picked[0].url, "a")


# ---------------------------------------------------------------- keyframes

class KeyframesSmokeTests(unittest.TestCase):
    def test_is_available_returns_bool(self) -> None:
        from core import keyframes
        self.assertIsInstance(keyframes.is_available(), bool)

    def test_extract_on_missing_file_returns_empty(self) -> None:
        from core.keyframes import extract_thumbnails
        self.assertEqual(extract_thumbnails(Path("/tmp/definitely-not.mp4"), n=3), [])
        # extract_for_cover should also survive the missing-file case.
        from core.keyframes import extract_for_cover
        self.assertIsNone(extract_for_cover(Path("/tmp/definitely-not.mp4")))


if __name__ == "__main__":
    unittest.main()
