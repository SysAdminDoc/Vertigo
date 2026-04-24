"""T3b · Segment proposals via local TextTiling.

**Goal** — on import of a long clip (>10 min), surface a ranked list of
candidate 30-90 s segments the user can jump their trim handles into.
The original ROADMAP line pointed at the ClipsAI fork; that library is
MIT but its dep chain drags in WhisperX + torch, which we refuse on
charter grounds. This module achieves the same product outcome with the
already-cached faster-whisper word stream plus numpy.

Charter compliance:
    * No LLM step. Ranking is a deterministic weighted sum over local
      signals (?-count, laughter, silence gap, length fit). "Stop
      before the LLM step" is the explicit charter line.
    * No network. Everything runs on the in-memory caption stream.
    * No new heavy dep. Pure stdlib (math, re, dataclass) — the
      TextTiling sweep is fast enough without numpy vectorisation.

Algorithm
---------

1. **Token stream** — flatten the caption list into
   ``(t, lowercase_word)``. Stop-words stripped via a tiny embedded
   set; no NLTK dependency.

2. **TextTiling-style cohesion** — slide two adjacent K-token windows
   over the stream and compute Jaccard similarity between their
   content-word sets. Low-similarity "valleys" are topic boundaries.
   Boundary candidates are also promoted when a silence gap
   (``gap_seconds``) appears between successive captions.

3. **Segment assembly** — walk the boundary list greedily, collecting
   adjacent topics until the running duration enters the
   ``[min_sec, max_sec]`` window, then emit a :class:`SegmentProposal`.

4. **Score** — weighted sum of:

   * ``questions`` — how many question-mark chunks the segment carries
     (engagement signal baked into 2026 creator research).
   * ``laughter`` — matches any of {haha, hehe, lol, [laughter], *laughs*}.
   * ``silence_gap_edge`` — whether a long silence abuts either side
     (good cut point → higher fidelity).
   * ``length_fit`` — triangular preference around ``target_sec``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .subtitles import Caption


# ---------------------------------------------------------------- tunables

DEFAULT_MIN_SEC = 30.0
DEFAULT_MAX_SEC = 90.0
DEFAULT_TARGET_SEC = 45.0
DEFAULT_TOP_N = 8
DEFAULT_MIN_CLIP_SEC_FOR_PROPOSALS = 600.0  # only propose on > 10 min clips

_WINDOW_TOKENS = 20         # TextTiling window size (content words)
_BOUNDARY_VALLEY_THRESHOLD = 0.35   # Jaccard <= this flags a topic boundary
_SILENCE_BOUNDARY_SEC = 2.5 # silence gap that promotes a boundary by itself

# A deliberately small stop-list. Keeping it inline means zero network /
# zero NLTK, and the set is stable across locales that matter for short-form.
# Contractions like "'ll" / "'s" are intentionally omitted because the
# tokenizer strips surrounding apostrophes and filters len<=1, so those
# forms never reach the stop-check in the first place.
_STOP_WORDS: frozenset[str] = frozenset(
    """
    a an and are as at be but by for from had has have he her him his how i
    in is it its just me my no not of on or our she so than that the their
    them there these they this to too us was we were what when where which
    who why will with would you your yours like do did does don doesn
    hey yeah ok okay oh uh um well right really
    """.split()
)

# Laughter / engagement token fingerprints.
_LAUGH_RE = re.compile(
    r"\b(haha+|hehe+|hihi+|lol|lmao|rofl|omg|wow+|yay+|woo+)\b|\[\s*laughter\s*\]|\*\s*laughs\s*\*",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(r"\?")
_WORD_RE = re.compile(r"[A-Za-z']+")


# ---------------------------------------------------------------- types


@dataclass(frozen=True)
class SegmentProposal:
    """A candidate 30-90 s jump-to-region with a human-readable hint."""

    start: float           # seconds in the source clip
    end: float
    title_hint: str        # first ~60 chars of the segment's transcript
    score: float           # 0..1
    questions: int
    laughter_hits: int
    silence_gap_before: float
    silence_gap_after: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# ---------------------------------------------------------------- public api


def propose_segments(
    captions: list[Caption],
    *,
    min_sec: float = DEFAULT_MIN_SEC,
    max_sec: float = DEFAULT_MAX_SEC,
    target_sec: float = DEFAULT_TARGET_SEC,
    top_n: int = DEFAULT_TOP_N,
) -> list[SegmentProposal]:
    """Return up to ``top_n`` ranked :class:`SegmentProposal` records.

    Empty caption lists and clips shorter than ``min_sec`` both return
    an empty list — callers should gate on clip duration before calling.
    """
    if not captions or target_sec <= 0 or min_sec <= 0 or max_sec <= min_sec:
        return []

    total_span = captions[-1].end - captions[0].start
    if total_span < min_sec:
        return []

    tokens = _token_stream(captions)
    if len(tokens) < _WINDOW_TOKENS * 2:
        # Too short for TextTiling — treat the whole clip as a single segment.
        segs = [(captions[0].start, captions[-1].end)]
    else:
        boundaries = _boundaries(tokens, captions)
        segs = _assemble_segments(boundaries, min_sec=min_sec, max_sec=max_sec, target_sec=target_sec)

    proposals: list[SegmentProposal] = []
    for seg_start, seg_end in segs:
        if seg_end - seg_start < min_sec:
            continue
        prop = _score_segment(seg_start, seg_end, captions, target_sec)
        # Drop pure-silence regions: a segment that covers a gap between
        # topic clusters and holds no transcribed content isn't a useful
        # jump-to candidate.
        if not prop.title_hint:
            continue
        proposals.append(prop)

    proposals.sort(key=lambda p: p.score, reverse=True)
    return proposals[:top_n]


def should_propose_for_duration(duration_sec: float) -> bool:
    """Gate: should the caller bother computing proposals at all?

    Surfaces the "only on clips > 10 min" ROADMAP charter in one place.
    """
    return duration_sec >= DEFAULT_MIN_CLIP_SEC_FOR_PROPOSALS


# ---------------------------------------------------------------- tokenisation


def _token_stream(captions: list[Caption]) -> list[tuple[float, str]]:
    """Flatten ``captions`` to ``(time, content_word)`` pairs.

    Uses per-word timings when available (karaoke preset), otherwise
    spreads words evenly across the caption span. Stop-words filtered.
    """
    tokens: list[tuple[float, str]] = []
    for cap in captions:
        text = cap.text or ""
        if cap.words:
            for w in cap.words:
                lower = w.text.lower()
                for m in _WORD_RE.finditer(lower):
                    tok = m.group(0).strip("'")
                    if tok and tok not in _STOP_WORDS and len(tok) > 1:
                        tokens.append((w.start, tok))
        else:
            matches = list(_WORD_RE.finditer(text.lower()))
            if not matches:
                continue
            span = max(1e-6, cap.end - cap.start)
            n = len(matches)
            for i, m in enumerate(matches):
                tok = m.group(0).strip("'")
                if tok and tok not in _STOP_WORDS and len(tok) > 1:
                    t = cap.start + (i / max(1, n - 1)) * span if n > 1 else cap.start
                    tokens.append((t, tok))
    return tokens


# ---------------------------------------------------------------- boundaries


def _boundaries(tokens: list[tuple[float, str]], captions: list[Caption]) -> list[float]:
    """TextTiling-style boundary timestamps, augmented with silence gaps."""
    out: set[float] = {captions[0].start, captions[-1].end}

    # 1) topic-shift valleys via Jaccard between adjacent windows
    K = _WINDOW_TOKENS
    for i in range(K, len(tokens) - K):
        left = {t for _, t in tokens[i - K:i]}
        right = {t for _, t in tokens[i:i + K]}
        if not left or not right:
            continue
        sim = len(left & right) / len(left | right)
        if sim <= _BOUNDARY_VALLEY_THRESHOLD:
            out.add(tokens[i][0])

    # 2) silence-gap boundaries (more reliable than pure lexical signal)
    for a, b in zip(captions, captions[1:]):
        gap = b.start - a.end
        if gap >= _SILENCE_BOUNDARY_SEC:
            # boundary sits on the *end* of the silence so the next segment
            # doesn't start mid-quiet-air
            out.add(b.start)

    sorted_bounds = sorted(out)
    # Dedup near-duplicates (< 0.5 s apart) so we don't fragment uselessly.
    tight: list[float] = []
    for b in sorted_bounds:
        if not tight or b - tight[-1] >= 0.5:
            tight.append(b)
    return tight


def _assemble_segments(
    boundaries: list[float],
    *,
    min_sec: float,
    max_sec: float,
    target_sec: float,
) -> list[tuple[float, float]]:
    """Walk boundary list forward, emitting segments that land in
    ``[min_sec, max_sec]`` — never crossing ``max_sec``. Greedy, not
    globally optimal, but deterministic and fast."""
    segs: list[tuple[float, float]] = []
    if len(boundaries) < 2:
        return segs

    i = 0
    while i < len(boundaries) - 1:
        start = boundaries[i]
        # pick the boundary that best matches target_sec but stays within max_sec
        best_j = i + 1
        best_score = math.inf
        found = False
        for j in range(i + 1, len(boundaries)):
            end = boundaries[j]
            span = end - start
            if span < min_sec:
                continue
            if span > max_sec:
                break
            score = abs(span - target_sec)
            if score < best_score:
                best_score = score
                best_j = j
                found = True
        if not found:
            # no boundary in-window; hard-cap at the nearest one above min_sec
            # even if it exceeds max_sec -> the scorer will dock it for length_fit.
            fallback_found = False
            for j in range(i + 1, len(boundaries)):
                if boundaries[j] - start >= min_sec:
                    best_j = j
                    fallback_found = True
                    break
            if not fallback_found:
                break
        segs.append((start, boundaries[best_j]))
        i = best_j
    return segs


# ---------------------------------------------------------------- scoring


def _score_segment(
    start: float,
    end: float,
    captions: list[Caption],
    target_sec: float,
) -> SegmentProposal:
    """Deterministic 0-1 score. Higher == stronger candidate."""
    inside = [c for c in captions if c.end > start and c.start < end]
    joined = " ".join(c.text for c in inside if c.text).strip()

    questions = len(_QUESTION_RE.findall(joined))
    laughter = len(_LAUGH_RE.findall(joined))

    # Silence-gap edges — reward segments flanked by quiet air; easier to cut.
    gap_before = _gap_before(start, captions)
    gap_after = _gap_after(end, captions)
    edge_bonus = 0.0
    if gap_before >= _SILENCE_BOUNDARY_SEC:
        edge_bonus += 0.15
    if gap_after >= _SILENCE_BOUNDARY_SEC:
        edge_bonus += 0.15

    # Length fit — triangular preference around target_sec.
    duration = max(0.0, end - start)
    length_fit = max(0.0, 1.0 - abs(duration - target_sec) / max(target_sec, 1e-6))

    # Base signal weighting — tuned so that a segment with both a question
    # and a laugh in the middle outranks a quiet segment purely on length.
    signal = (
        min(1.0, questions / 3.0) * 0.40
        + min(1.0, laughter / 2.0) * 0.20
        + length_fit * 0.40
    )

    score = min(1.0, max(0.0, signal + edge_bonus))

    reasons: list[str] = []
    if questions:
        reasons.append(f"{questions} question" + ("s" if questions != 1 else ""))
    if laughter:
        reasons.append(f"{laughter} laugh-hit" + ("s" if laughter != 1 else ""))
    if gap_before >= _SILENCE_BOUNDARY_SEC:
        reasons.append("silence before")
    if gap_after >= _SILENCE_BOUNDARY_SEC:
        reasons.append("silence after")
    if length_fit > 0.85:
        reasons.append("ideal length")

    title_hint = _title_hint_from(joined)

    return SegmentProposal(
        start=start,
        end=end,
        title_hint=title_hint,
        score=float(score),
        questions=questions,
        laughter_hits=laughter,
        silence_gap_before=gap_before,
        silence_gap_after=gap_after,
        reasons=tuple(reasons),
    )


def _gap_before(t: float, captions: list[Caption]) -> float:
    """Silence duration immediately preceding ``t``.

    Walks forward until the pair ``(a, b)`` straddles ``t`` — i.e.
    ``a.end <= t <= b.start`` — and returns ``b.start - a.end``. If
    ``t`` lands inside a caption (no straddling pair) the gap is zero.
    Returns zero on empty / single-entry input.
    """
    for a, b in zip(captions, captions[1:]):
        if a.end <= t <= b.start:
            return max(0.0, b.start - a.end)
        if b.start > t:
            # past the crossing; no straddling gap
            return 0.0
    return 0.0


def _gap_after(t: float, captions: list[Caption]) -> float:
    """Silence duration immediately following ``t``.

    Mirror of :func:`_gap_before` — finds the pair where ``t`` sits on
    or after ``a.end`` and before ``b.start`` and returns that gap.
    """
    for a, b in zip(captions, captions[1:]):
        if a.end <= t <= b.start:
            return max(0.0, b.start - a.end)
        if a.end > t:
            return 0.0
    return 0.0


def _title_hint_from(joined: str, *, max_len: int = 60) -> str:
    """First sentence-ish slice, capped at ``max_len``."""
    cleaned = " ".join(joined.split())
    if not cleaned:
        return ""
    # End at the first terminal punctuation we find inside the cap.
    for end in ("?", ".", "!"):
        idx = cleaned.find(end, 5)
        if 0 <= idx < max_len:
            return cleaned[: idx + 1].strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len - 1].rstrip() + "\u2026"
