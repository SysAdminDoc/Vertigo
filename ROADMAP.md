# ReelForge / Vertigo Roadmap

Vertical video studio (PyQt6 + FFmpeg + MediaPipe) that turns any footage into 9:16 for Shorts/TikTok/Reels. Roadmap deepens Smart Track intelligence, adds audio tooling, and aims at a full short-form pipeline.

## Planned Features

### Reframe / Tracking
- Multi-subject tracking with manual pick ("follow the left person")
- Pose + gesture-aware reframe (MediaPipe Pose) beyond face detection
- Saliency-driven reframe for non-human subjects (DeepGaze / FastSal WebGPU)
- Manual keyframe override track (drag points on a timeline, overrides auto)
- Per-scene reframe mode override

### Audio
- Auto-ducking music under speech
- Loudness normalization to -14 LUFS / -16 LUFS presets
- Background music library picker with license field
- Voice enhance (RNNoise / DeepFilterNet)
- Silence auto-cut with configurable threshold + padding

### Captions
- Word-level highlight (active word pops) — TikTok style
- Emoji augmentation (auto-insert relevant emoji per sentence, opt-in)
- Font + style preset library
- Multi-language transcription + translation (Whisper + NLLB)
- SRT export alongside burn-in

### Overlays & Motion
- Animated stickers / GIF overlays with time range
- B-roll inserts (drag footage onto a second track)
- Zoom / pan ("Ken Burns") keyframe overlay per clip
- Logo / watermark batch apply
- Countdown / reveal templates

### Publishing
- Platform upload helpers (local staging folders named per platform)
- Auto-generate variants (9:16, 1:1, 16:9) from one edit
- Title / description / hashtag notepad attached to each clip
- Thumbnail grabber (frame picker → 9:16 PNG)
- Export manifest (CSV with filenames, durations, platforms)

### Engine
- Preview proxy workflow (low-res preview, hi-res on export)
- GPU-accelerated preview via `pyav` + QRhi or shaders
- Save project `.reelforge` JSON with re-openable timeline
- Crash-safe autosave every 30s

## Competitive Research
- **Opus Clip / Vidyo.ai / Submagic** — paid AI reframe SaaS. Lesson: their wedge is auto-highlight-picking from long-form; add a "find the best 60s" feature.
- **CapCut** — free + full editor, closed. Lesson: caption UX is the bar. Match it.
- **Premiere Auto Reframe** — Adobe baseline. Lesson: local-first + free + scriptable beats Adobe's subscription.
- **Descript** — audio-first editor, great silence cut. Lesson: borrow silence cut + transcript-edit-drives-video UX.

## Nice-to-Haves
- Project templates (podcast-clip, talking-head, gameplay, tutorial)
- Live preview while Smart Track is still analyzing
- Cloud render offload (user-bring-their-own remote FFmpeg)
- Plugin API for custom overlay generators
- Remote control app (phone → pick clip → export)
- Localization pass
