# Changelog

All notable changes to ReelForge are documented here.

## [0.4.0] - 2026-04-22

### Added
- **Brand mark** — procedural logo rendered by `assets/build_icons.py` (Pillow). Ships as `icon.svg`, `icon.ico` (16/32/48/128/256 multi-res), `icon.png` (256), plus 512px and 16-48 PNG variants. Wordmark SVG included separately.
- **Window icon wiring** — `QApplication.setWindowIcon`, `MainWindow.setWindowIcon`, and the frameless titlebar all pick the icon up via a new bundle-aware `ui/assets.py` resolver that works under both source and PyInstaller.
- **Text overlays tab (Text)** — per-overlay editor with text, in/out range (clamped to clip duration), placement (title / top strap / lower-third / bottom caption), font size, color picker, and remove button. Preset menu adds intro title card, lower-third name, top hook, and bottom CTA with one click. Overlays compile to an FFmpeg `drawtext=` filter chain with `enable='between(t,start,end)'` gating.
- **PyInstaller spec** — `reelforge.spec` produces a single-file exe on every OS with the correct per-platform icon, bundles `assets/` and MediaPipe's TFLite data files, and trims ~350 MB of deadweight (tkinter, matplotlib, scipy, pandas, torch, tensorflow). faster-whisper stays excluded from the bundle and lazy-installs at runtime.
- **GitHub Actions CI** — `.github/workflows/build.yml` builds for Windows, macOS arm64, and Linux on every tag push or `workflow_dispatch`. Packages artifacts as `ReelForge-<os>-<arch>.{zip,tar.gz}` and uploads them via `gh release upload --clobber`, auto-creating a draft release if one doesn't exist.

### Changed
- `core/reframe.build_plan` now accepts `overlays=list[TextOverlay]` and chains a `drawtext=` filter pipeline after reframe/adjustments.
- README shows the logo, describes overlays + binary builds, updates architecture tree.
- Version bumped to 0.4.0; README badge + `__version__` updated.

### Verified
- Two-overlay encode (title card 0–1.5s + lower-third 1.5–3s) renders cleanly (`rc=0`).
- `icon.ico` loads 5 sizes (16/32/48/128/256) into `QIcon`.
- All 6 sidebar tabs (Queue / Adjust / Track / Output / Captions / Text) construct without error.

## [0.3.0] - 2026-04-22

### Added
- **Output tab** — pick encoder, quality (1–100 slider mapped into native codec units), and speed preset. Auto-detects every encoder FFmpeg exposes:
  - NVIDIA NVENC (H.264 + HEVC)
  - Intel QuickSync Video (H.264 + HEVC)
  - AMD AMF (H.264 + HEVC)
  - Apple VideoToolbox (H.264 + HEVC)
  - libx264 / libx265 (CPU fallback)
- **Captions tab** — AI subtitle generation via `faster-whisper`. Lazy-installed on first use (~200 MB one-time download) so the default bootstrap stays fast. Supports every Whisper model size (`tiny` through `large-v3`), 10+ language overrides or auto-detect, and mobile-safe burn-in styling (Segoe UI 24pt, bold, outlined, centered, 60 px bottom margin).
- Per-clip subtitle cache — generated SRTs persist across clip switches in the queue.
- Subtitle burn-in wired into the FFmpeg filter chain via `subtitles=` with cross-platform path escaping (Windows drive letter handling).

### Changed
- `EncodeJob` extended with `encoder`, `quality`, `speed_preset`, `subtitles_path`, `burn_subtitles` fields.
- `core/encode.py` no longer hardcodes libx264 — it consumes the chosen encoder via `core.encoders.encoder_args()`.
- Version bumped to 0.3.0; README badge + `__version__` in `reelforge.py` updated.

### Verified
- Smoke tested CPU (libx264) and NVENC hardware encodes with `-cq`/`-crf` quality mapping.
- Subtitle burn-in renders a 2s test clip with an SRT overlay cleanly (rc=0).
- All 5 sidebar tabs (Queue / Adjust / Track / Output / Captions) construct without error under the new theme system.

## [0.2.0] - 2026-04-22

### Added
- **Batch queue** — drop multiple clips at once, queue panel with per-item status (pending / active / done / failed), click any entry to preview, **Export All** runs them sequentially to a chosen folder.
- **Trim timeline** — dual-thumb range slider on the preview, drag in/out markers; playhead seeks by clicking the track. Exports respect the trim window.
- **Scene-aware Smart Track** — PySceneDetect (with histogram fallback) segments the timeline into scenes; per-scene median viewport locks the camera inside each cut so the pan never crosses a hard transition.
- **Adjustments panel** — brightness / contrast / saturation sliders with live value readouts; applied via FFmpeg `eq=` filter appended to the reframe chain.
- **Tabbed sidebar** — QUEUE · ADJUST · TRACK tabs in the right column.
- **Logo prompts** — five AI image generator prompts for minimal icon, app icon, wordmark, emblem, and abstract marketing art (`assets/logo_prompts.md`).

### Changed
- Version bumped to 0.2.0; README badge + `__version__` in `reelforge.py` updated.
- Removed `ffmpeg-python` dependency — we were calling FFmpeg via `subprocess` directly.

### Verified
- All four reframe modes still encode clean MP4s end-to-end.
- Smart Track now renders with scene-clamped keyframes when scenes are detected.
- Trim start/end respected by FFmpeg `-ss` / `-t` args.

## [0.1.0] - 2026-04-22

### Added
- Initial release.
- Premium PyQt6 GUI with Catppuccin Mocha theme, custom frameless titlebar, glassmorphism panels, shimmer headings, hover lifts.
- Drag-drop video import with animated drop zone.
- Built-in preview player with scrubber.
- Four reframe modes:
  - **Center Crop** — fast center-column crop, zero analysis.
  - **Smart Track** — MediaPipe face detection, pan viewport to follow subjects.
  - **Blur Letterbox** — keeps full frame, fills sides with blurred background.
  - **Manual** — drag viewport to lock crop column.
- Output presets for YouTube Shorts, TikTok, Instagram Reels, and Square (1:1).
- Async FFmpeg encoding with real-time progress bar and log overlay.
- Auto-install bootstrap for first-run dependency setup.
- Turnkey — drops into any FFmpeg-enabled system with a single `python reelforge.py`.
