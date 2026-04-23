# Vertigo — Roadmap

Prioritized from a three-stream competitive research pass against the
2026 OSS vertical-video / caption / auto-clip landscape. Each item has
an honest impact × effort estimate, a source project, and a licensing
note. Items are ordered within each tier by ROI.

Ticked items shipped in the matching version.

---

## Tier 1 · Captions leap — ship-this-sprint [~6–10 h]

Goal: move captions from *acceptable* to *best-in-class for 9:16*.

- [x] **T1a · Mobile-correct defaults** · ~1 h · v0.8.0
  Font size `height / 22` (≈ 87 pt at 1080 p), bottom margin `0.20 ×
  height`, 2-line × ≤ 18-char wrap, 3–4-word chunks capped at 1.2 s.
  2026 creator-tool consensus (CapCut / Opus / Submagic / Descript).

- [x] **T1b · Caption preset system** · ~3 h · v0.8.0
  `CaptionPreset` dataclass + `QComboBox` with live preview. Six
  bundled looks: *Clean · Pop · Karaoke · Bold Yellow · Neon Outline
  · Classic*. Replaces the single hard-coded ASS block.

- [x] **T1c · Word-level karaoke** · ~3 h · v0.8.0 · stable-ts (MIT)
  Flip `faster-whisper` to `word_timestamps=True` (no new deps) and
  port `stable_whisper/text_output.py::result_to_ass` so each word
  gets a `\kf` fill-sweep. libass renders it through the existing
  `subtitles=` filter.

---

## Tier 2 · Smart-track quality — next sprint [~8–12 h]

Goal: lift Smart Track from "naive piecewise-lerp" to "competitive
with `mutonby/openshorts` while keeping Vertigo's uniquely fast
expression-driven crop + 4-backend hardware encoding".

- [x] **T2b · Savitzky-Golay trajectory smoothing** · ~1 h · v0.8.0 · `scipy`
  Single `savgol_filter(x_series, window_length=odd(fps·0.5),
  polyorder=3)` call before emitting the FFmpeg `x(t)` expression.
  Kills micro-jitter; scipy already a MediaPipe transitive.

- [x] **T2c · VFR → CFR pre-pass + audio start-time fix** · ~2 h · v0.8.0
  Every competitor silently ships an audio-drift bug on VFR sources
  and streams with non-zero `start_time`. `ffprobe` compares
  `r_frame_rate` vs `avg_frame_rate`; if they differ, normalise to
  CFR. Video `start_time` is fed as `-ss` on the audio extract.
  **License caveat:** `Autocrop-vertical` has no LICENSE →
  re-implement from the public `ffprobe` technique, do not copy.

- [x] **T2a · `SmoothedCameraman` + `SpeakerTracker` port** · ~4–6 h · v0.8.0 · openshorts (MIT)
  Two classes, ~300 LoC total. Safe-zone hysteresis (viewport holds
  still while subject stays within 25 % of crop width), speed-adaptive
  motion (3 px/f normal, 15 px/f for > 50 % jumps, overshoot clamp),
  ID-sticky speaker tracking (exp. decay 0.85/f, 3× sticky bonus,
  30-frame switch cool-down).

- [x] **T2d · `--plan-only` dry-run** · ~1–2 h · v0.8.0
  Print the per-scene `TRACK / LETTERBOX / CENTER` strategy table
  without encoding. QA/preview feature in the sidebar before
  committing a long encode.

---

## Tier 3 · Narrow auto-highlight funnel [~6–10 h]

Scope call: *segment proposals + shot-aware trimming + hook-energy*
is a natural upstream extension that funnels into the existing
single-clip editor. *LLM-viral-scoring + thumbnails + uploads* is
OpusClip's lane — every OSS attempt is mediocre. Build the former,
never the latter.

- [x] **T3a · Shot-snap on trim timeline** · ~3 h · v0.9.0 · existing PySceneDetect
  Scope changed from transnetv2-pytorch to the PySceneDetect we
  already ship — 500 MB PyTorch dep wasn't worth the +4 % F1. New
  `SceneWorker` runs on every clip load; `RangeSlider` draws
  subtle tick marks at each cut and magnet-snaps trim handles
  within 200 ms. Scene list also reused by Smart Track so the
  inline pass is skipped when the background worker has finished.

- [ ] **T3b · Segment proposals via ClipsAI TextTiling** · ~3 h · ClipsAI (MIT, fork — upstream dead)
  On import of > 10 min clips, produce a side panel of candidate
  30–90 s segments with transcript previews. TextTiling boundaries
  on WhisperX word stream, ranked by `?`-count, laughter tokens,
  silence-gap heuristics. **Stop before the LLM step.**

- [x] **T3c · Hook-energy score** · ~1 h · v0.9.0 · no new deps
  `core/hook_score.py` produces a 0–100 "first-3-second" score from
  FFmpeg-extracted 16 kHz mono PCM + per-frame RMS/ZCR voice
  heuristic. Surfaced in the dry-run report as `Hook (first 3s)`.
  Deliberately ignored the `librosa + silero-vad` suggestion — no
  need for torch just to RMS a 3-second window.

---

## Tier 4 · Power-user opt-in [gated behind toggles]

- [ ] **T4a · Face-aware caption positioning** · ~4 h · MediaPipe (already pulled)
  Sample 2 fps, emit `\pos(x, y)` overrides on Dialogue lines so
  captions never overlap the face. Falls back to safe-area default.
  Depends on T2a face-tracker plumbing.

- [ ] **T4b · Pyannote speaker diarization** · ~4–6 h · WhisperX (BSD-2) + pyannote (MIT)
  One ASS style per speaker with a distinct `PrimaryColour`. Gated
  behind toggle — HF token + EULA click + ~500 MB model, lazy-
  installed like faster-whisper.

- [ ] **T4c · Lighthouse moment-retrieval** · ~6–8 h · line/lighthouse (Apache-2)
  QD-DETR text-query highlights ("the funny part about dogs" →
  ranked timestamps). Power-user feature; 1–2 GB model, GPU-preferred.
  Only real 2024–26 research that actually works vs commercial.

---

## Skip-list — all three research streams converged on these

| Item | Why skip |
|---|---|
| `linto-ai/whisper-timestamped` | **AGPL-3.0** — poisons Vertigo's MIT licence. |
| `gauravzazz/smart-reframe` | 0 stars, 1 commit, empty README. Dead. |
| `IORoot/AI__autoflip` | Stale Docker wrapper around Google AutoFlip. |
| `bmezaris/RetargetVid` direct port | Dead since 2022, TF1 + CUDA + UNISAL. Only the scipy-smoothing idea is borrowable (T2b). |
| Copying `kamilstanuch/Autocrop-vertical` source | No LICENSE file → legally all-rights-reserved. Re-implement public techniques only. |
| `whisper.cpp` swap | Loses `faster-whisper`'s Python word-timestamp API, adds binary build step. |
| `moviepy` caption burn | Slower than libass via `subtitles=`. |
| AutoShot over TransNetV2 | +4 % F1 isn't worth research-code integration pain. |
| LLM-based "viral moment" scoring | Coin flip + API cost. Every OSS clone ships it; all are mediocre. Ship proposals; let users pick. |
| Full OBS auto-highlight plugin | Zero OSS precedent worth forking, out of scope. |

---

## What Vertigo already does better than every audited competitor

- Hardware-encoder auto-detect across **4 backends** (NVENC / QSV /
  AMF / VideoToolbox). Autocrop-vertical has 2; openshorts has 0.
- Single expression-driven `crop=w:h:x(t):0` — every other project
  re-encodes via raw BGR24 pipe, ~2–4× slower.
- **Four** explicit reframe modes including Manual Crop — no
  competitor has this.
- PyQt6 batch queue + trim timeline + colour grading + text overlay
  editor — all competitors are CLI or web.
- Turnkey bootstrap, frameless premium UI, three themes, painted
  mode-card icons, focus-state-without-layout-shift — UX-wise none
  of the competition is close.

## Open-Source Research (Round 2)

### Related OSS Projects
- https://github.com/gauravzazz/smart-reframe — MediaPipe face + audio-activity cinematic pan, asymmetric smoothing, group-widen
- https://github.com/mutonby/openshorts — Dual TRACK (MediaPipe + YOLOv8) / GENERAL (blur BG) mode, faster-whisper burned captions
- https://github.com/RafaelGodoyEbert/ViralCutter — Opus Clip alternative, WhisperX GPU, Gemini/GPT/Llama hook-finder, "Hormozi" word-burn captions
- https://github.com/kamilstanuch/Autocrop-vertical — PySceneDetect + YOLOv8 per-scene TRACK vs LETTERBOX strategy decision
- https://github.com/aregrid/frame — Cursor-style conversational video editor, AI-powered
- https://github.com/Vhonowslend/StreamFX-Public — OBS real-time auto-framing ML filter (reference for live pipeline)
- https://github.com/topics/auto-reframe-video — Topic index
- https://github.com/topics/vertical-video — Topic index with OTIO/EDL export + transcript-based editing projects

### Features to Borrow
- Audio-activity-weighted tracking — move viewport toward active speaker, not just faces (smart-reframe)
- Asymmetric smoothing — fast zoom-out, slow cinematic zoom-in to avoid crop-outs (smart-reframe)
- Group-aware widen — auto-widen when 2+ people interact (smart-reframe)
- Scene-boundary-aware keyframes via PySceneDetect — never cross a hard cut (Autocrop-vertical, already partial)
- YOLOv8 person detection as fallback/alternative to MediaPipe face — non-frontal / full-body shots (Autocrop-vertical, openshorts)
- Per-scene TRACK vs LETTERBOX auto-decision based on subject count/position (Autocrop-vertical)
- Burned-in word-level captions via faster-whisper + "Hormozi" styled highlight (openshorts, ViralCutter)
- LLM hook-finder — auto-cut long-form into 30-60s viral segments (ViralCutter)
- OTIO / EDL / XML export for Resolve/Premiere handoff (vertical-video topic)

### Patterns & Architectures Worth Studying
- Scene-graph pipeline (detect -> score -> strategy -> render) over monolithic per-frame loop (Autocrop-vertical)
- Async GPU worker + CPU preview via faster-whisper int8 quant for real-time caption draft (openshorts)
- Local-first LLM adapter layer (Ollama/Llama/Gemini/GPT switchable via config) (ViralCutter)
- MediaPipe landmark -> Kalman filter -> spring-damped viewport (smart-reframe)
- Remotion-style declarative video render as an export backend for burned overlays (claude-videoedit cross-ref)
