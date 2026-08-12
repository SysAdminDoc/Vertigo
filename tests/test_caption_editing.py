"""Caption timing review operations and sidecar persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.caption_editing import (
    CaptionEditError,
    merge_captions,
    shift_captions,
    split_caption,
    split_captions,
    write_edited_sidecar,
)
from core.caption_types import Caption, Word
from core.caption_styles import resolve


def _caption() -> Caption:
    return Caption(
        1.0,
        5.0,
        "one two three",
        (
            Word(1.0, 2.0, "one"),
            Word(2.0, 3.0, "two"),
            Word(3.0, 5.0, "three"),
        ),
    )


class CaptionEditingTests(unittest.TestCase):
    def test_shift_selected_preserves_input_and_word_timings(self) -> None:
        captions = [_caption(), Caption(6.0, 7.0, "next")]

        edited = shift_captions(captions, 0.25, indices=[0])

        self.assertEqual(captions[0].start, 1.0)
        self.assertEqual(edited[0].start, 1.25)
        self.assertEqual(edited[0].end, 5.25)
        self.assertEqual(edited[0].words[1].start, 2.25)
        self.assertEqual(edited[1], captions[1])

    def test_negative_shift_clamps_the_whole_chunk_at_zero(self) -> None:
        shifted = shift_captions([_caption()], -2.0)[0]

        self.assertEqual(shifted.start, 0.0)
        self.assertEqual(shifted.end, 4.0)
        self.assertEqual(shifted.words[0].start, 0.0)

    def test_split_uses_word_boundary_and_merge_round_trips(self) -> None:
        left, right = split_caption(_caption())

        self.assertEqual((left.start, left.end), (1.0, 3.0))
        self.assertEqual((right.start, right.end), (3.0, 5.0))
        self.assertEqual(left.text, "one two")
        self.assertEqual(right.text, "three")
        self.assertEqual(merge_captions([left, right], 0), [_caption()])

    def test_plain_text_split_can_use_explicit_position(self) -> None:
        caption = Caption(2.0, 8.0, "alpha beta gamma delta")

        left, right = split_caption(caption, 5.0)

        self.assertEqual(left, Caption(2.0, 5.0, "alpha beta"))
        self.assertEqual(right, Caption(5.0, 8.0, "gamma delta"))

    def test_split_rejects_single_word(self) -> None:
        with self.assertRaises(CaptionEditError):
            split_captions([Caption(0.0, 2.0, "single")], 0)

    def test_sidecar_writer_keeps_srt_and_ass_formats(self) -> None:
        captions = [_caption()]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt = write_edited_sidecar(captions, root / "captions.vertigo.srt")
            ass = write_edited_sidecar(
                captions,
                root / "captions.vertigo.ass",
                preset=resolve("karaoke"),
                height_px=1920,
                width_px=1080,
            )

            self.assertIn("00:00:01,000 --> 00:00:05,000", srt.read_text())
            ass_text = ass.read_text()
            self.assertIn("PlayResX: 1080", ass_text)
            self.assertIn("Dialogue: 0,0:00:01.00,0:00:02.00", ass_text)
            self.assertIn(r"{\kf100}one", ass_text)


if __name__ == "__main__":
    unittest.main()
