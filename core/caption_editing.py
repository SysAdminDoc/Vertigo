"""Small, local edits for a transcribed caption timeline.

The transcription pipeline keeps :class:`~core.caption_types.Caption` and
:class:`~core.caption_types.Word` immutable.  This module therefore returns
new lists for every edit, which keeps the review UI predictable and makes it
safe to discard an unsaved adjustment without mutating the cached transcript.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from pathlib import Path

from .caption_types import Caption, Word


MIN_CAPTION_DURATION = 0.05


class CaptionEditError(ValueError):
    """Raised when a requested timeline edit cannot produce two valid chunks."""


def shift_caption(
    caption: Caption,
    offset: float,
    *,
    min_duration: float = MIN_CAPTION_DURATION,
) -> Caption:
    """Return ``caption`` shifted by seconds, clamped at time zero.

    When a negative nudge would move the start before zero, the whole caption
    (including word timings) is shifted by the smaller effective offset so its
    duration is preserved.  The minimum duration only protects malformed or
    extremely short source chunks.
    """

    offset = _finite_number(offset, "offset")
    min_duration = max(0.001, _finite_number(min_duration, "min_duration"))
    delta = offset
    new_start = max(0.0, float(caption.start) + delta)
    delta = new_start - float(caption.start)
    new_end = max(new_start + min_duration, float(caption.end) + delta)
    words = tuple(_shift_word(word, delta, min_duration) for word in caption.words)
    return Caption(new_start, new_end, caption.text, words)


def shift_captions(
    captions: Sequence[Caption],
    offset: float,
    *,
    indices: Iterable[int] | None = None,
    min_duration: float = MIN_CAPTION_DURATION,
) -> list[Caption]:
    """Shift every caption or only the zero-based ``indices`` provided."""

    result = list(captions)
    selected = set(range(len(result))) if indices is None else set(indices)
    if any(index < 0 or index >= len(result) for index in selected):
        raise IndexError("caption index is outside the transcript")
    for index in selected:
        result[index] = shift_caption(
            result[index], offset, min_duration=min_duration
        )
    return result


def split_caption(
    caption: Caption,
    at: float | None = None,
    *,
    min_duration: float = MIN_CAPTION_DURATION,
) -> tuple[Caption, Caption]:
    """Split one caption at a word boundary or a simple text midpoint.

    Word-level transcripts use the nearest word boundary to ``at``.  Plain
    SRT chunks split their whitespace-delimited text near ``at`` (or at the
    temporal midpoint when no position is supplied).  The result keeps the
    original coverage, so a gap is never introduced by the edit.
    """

    min_duration = max(0.001, _finite_number(min_duration, "min_duration"))
    start = float(caption.start)
    end = float(caption.end)
    if end <= start:
        raise CaptionEditError("caption must have a positive duration")

    requested = (start + end) / 2.0 if at is None else _finite_number(at, "at")
    if caption.words and len(caption.words) >= 2:
        boundary_index = min(
            range(1, len(caption.words)),
            key=lambda index: abs(float(caption.words[index].start) - requested),
        )
        split_at = float(caption.words[boundary_index].start)
        left_words = tuple(caption.words[:boundary_index])
        right_words = tuple(caption.words[boundary_index:])
        left_text = " ".join(word.text for word in left_words).strip()
        right_text = " ".join(word.text for word in right_words).strip()
    else:
        tokens = caption.text.split()
        if len(tokens) < 2:
            raise CaptionEditError("caption needs at least two words to split")
        ratio = max(0.0, min(1.0, (requested - start) / (end - start)))
        split_index = max(1, min(len(tokens) - 1, round(len(tokens) * ratio)))
        split_at = requested
        left_words = ()
        right_words = ()
        left_text = " ".join(tokens[:split_index])
        right_text = " ".join(tokens[split_index:])

    if (
        split_at <= start + min_duration
        or split_at >= end - min_duration
        or not left_text
        or not right_text
    ):
        raise CaptionEditError("split point would create an empty or tiny chunk")

    return (
        Caption(start, split_at, left_text, left_words),
        Caption(split_at, end, right_text, right_words),
    )


def split_captions(
    captions: Sequence[Caption],
    index: int,
    at: float | None = None,
    *,
    min_duration: float = MIN_CAPTION_DURATION,
) -> list[Caption]:
    """Replace the caption at ``index`` with two edited chunks."""

    if index < 0 or index >= len(captions):
        raise IndexError("caption index is outside the transcript")
    left, right = split_caption(captions[index], at, min_duration=min_duration)
    return list(captions[:index]) + [left, right] + list(captions[index + 1 :])


def merge_captions(captions: Sequence[Caption], index: int) -> list[Caption]:
    """Merge the caption at ``index`` with the following chunk."""

    if index < 0 or index + 1 >= len(captions):
        raise IndexError("caption needs a following chunk to merge")
    first = captions[index]
    second = captions[index + 1]
    words = tuple(sorted((*first.words, *second.words), key=lambda word: word.start))
    merged = Caption(
        min(float(first.start), float(second.start)),
        max(float(first.end), float(second.end)),
        " ".join(part for part in (first.text.strip(), second.text.strip()) if part),
        words,
    )
    return list(captions[:index]) + [merged] + list(captions[index + 2 :])


def write_edited_sidecar(
    captions: Sequence[Caption],
    out_path: Path,
    *,
    preset=None,
    height_px: int = 1920,
    width_px: int | None = None,
) -> Path:
    """Atomically write edited captions using the existing sidecar format."""

    from .caption_styles import default_preset
    from .subtitles import write_ass, write_srt

    path = Path(out_path)
    caption_list = list(captions)
    if path.suffix.lower() == ".ass":
        return write_ass(
            caption_list,
            path,
            preset or default_preset(),
            height_px,
            width_px=width_px,
        )
    return write_srt(caption_list, path)


def _shift_word(word: Word, delta: float, min_duration: float) -> Word:
    start = max(0.0, float(word.start) + delta)
    end = max(start + min_duration, float(word.end) + delta)
    return Word(start, end, word.text)


def _finite_number(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


__all__ = [
    "CaptionEditError",
    "MIN_CAPTION_DURATION",
    "merge_captions",
    "shift_caption",
    "shift_captions",
    "split_caption",
    "split_captions",
    "write_edited_sidecar",
]
