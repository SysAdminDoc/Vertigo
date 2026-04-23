# Changelog

All notable changes to Vertigo are documented here.

## [0.6.1] - 2026-04-23

### Fixed
- **Critical — PyInstaller binary crashed on launch with `AttributeError: 'NoneType' object has no attribute 'write'`.** Two bugs stacked:
  1. Under a Windows GUI PyInstaller build (`console=False`), `sys.stderr` and `sys.stdout` are both `None`. The existing `sys.stderr.write(...)` call inside `_bootstrap()` therefore exploded *while reporting a different error* — swallowing the real message.
  2. The real message was `mediapipe: ModuleNotFoundError: No module named 'matplotlib'`. MediaPipe imports matplotlib internally; the spec had matplotlib in its `excludes` list to keep the binary small, which broke MediaPipe at bundle-import time.
- New `_fatal(title, body)` helper in `vertigo.py`:
  - Writes every fatal error to `%LOCALAPPDATA%\Vertigo\crash.log` (macOS: `~/Library/Logs/Vertigo`; Linux: `~/.local/state/Vertigo`).
  - Echoes to `sys.stderr` only when it is not `None`.
  - Pops a native Windows `MessageBoxW` so GUI-mode users actually see the failure.
  - Exits cleanly with a distinct code (2/3/4/10) per failure class.
- Replaced every raw `sys.stderr.write(...)` and `print(...)` in `_bootstrap()` / `_check_ffmpeg()` with the new helper.
- Wrapped `main()` in an `_entry()` guard so a late-import or Qt-init crash still surfaces a MessageBox instead of closing the GUI silently.
- `_REQUIRED` import loop now catches `Exception`, not just `ImportError`, so modules that fail at init time (not just missing ones) also report cleanly.

### Changed
- `matplotlib` and `scipy` removed from PyInstaller `excludes` — both are transitive MediaPipe dependencies. Binary size increases by ~40 MB on Windows; acceptable trade for correctness.
- `vertigo.spec` now runs `collect_submodules("scenedetect" | "cv2" | "PIL")` + `collect_data_files("scenedetect" | "cv2")` in addition to the existing MediaPipe collection, to preempt the next lazy-import miss.
- Explicit hiddenimports for every `scenedetect.detectors.*` submodule (content/threshold/adaptive/hash/histogram) — PySceneDetect loads detectors via string reference, which PyInstaller's static analyzer can't follow.

### Verified
- Rebuilt `Vertigo.exe` launches cleanly on Windows 11. Process monitoring shows exactly two PIDs (bootloader + runtime), runtime stabilizes at ~198 MB with the Qt main window visible, no crash log written, killed cleanly.
- No `'NoneType' object has no attribute 'write'` regression.

## [0.6.0] - 2026-04-22

### Changed
- **Renamed the project from Kiln to Vertigo.** Vertigo, from the Latin *vertere* ("to turn"), captures the tool's core verb: turning horizontal footage into vertical. It also lends the brand a cinematic identity — Hitchcock-era graphic design language (concentric circles, dolly-zoom perspective) translates cleanly into the mauve-to-pink accent system.
- Entry point is now `python vertigo.py` (was `python kiln.py`). PyInstaller output binaries are `Vertigo.exe` / `Vertigo.app` / `Vertigo`. macOS bundle identifier is `com.sysadmindoc.vertigo`.
- `QSettings` organization key is now `Vertigo`. Theme preference lookup walks a chained fallback: `Vertigo → Kiln → ReelForge → "system"`, so users who installed under any prior name keep their appearance.
- Qt app-property keys renamed (`kilnThemeId` → `vertigoThemeId`, same for `kilnThemePreference`).
- Cache / sidecar paths renamed (`.kiln/` → `.vertigo/`, `*.kiln.srt` → `*.vertigo.srt`).
- Titlebar brand label reads **Vertigo**; subtitle reads "Vertical video studio."
- Wordmark SVG redrawn for `VERTIGO`; `assets/logo_prompts.md` rewritten around the vertigo / rotation / dolly-zoom metaphor.
- README, architecture tree, install instructions, and CHANGELOG header updated.

### Verified
- App boots under every theme with the new brand mark, 6 sidebar tabs intact.
- End-to-end encode still produces a clean MP4 in all reframe modes.
- No stale `Kiln` / `kiln` references remain outside the deliberate legacy-fallback chain and historical changelog entries.

## [0.5.1] - 2026-04-22

### Fixed
- **Critical — PyInstaller fork-bomb on Windows.** The v0.5.0 binary relaunched itself recursively on startup because `multiprocessing.freeze_support()` was not called at the entry point. MediaPipe and cv2 both use Python's `multiprocessing` module internally; on Windows each worker spawns via `sys.executable`, which in a frozen build is `Kiln.exe` — so every worker booted a new GUI instead of a worker, spawning new workers, and so on. Two guards now prevent this:
  1. `multiprocessing.freeze_support()` is now the first executable statement in `kiln.py`.
  2. A PyInstaller runtime hook (`assets/runtime_hook_mp.py`) fires the same call *before* user code, wired into `kiln.spec` via `runtime_hooks=[...]`.
- **Bootstrap disabled in frozen builds.** `_bootstrap()` used to call `[sys.executable, "-m", "pip", "install", ...]` whenever a package import failed. In a frozen exe `sys.executable` is the GUI itself, so a missing bundled dep would have re-launched Kiln in a loop instead of running pip. `_bootstrap()` and `_pip_install()` now short-circuit when `sys.frozen` is set and print a clear "bundled import failed" error instead.
- **Version bumped to 0.5.1** everywhere (`__version__`, README badge, macOS `CFBundleShortVersionString` / `CFBundleVersion`).

### Rebuild required
Anyone who downloaded the v0.5.0 binary should kill any running `Kiln.exe` processes (Task Manager or `taskkill /F /IM Kiln.exe /T`) and replace the binary with the v0.5.1 release once CI finishes.

## [0.5.0] - 2026-04-22

### Changed
- **Renamed the project from ReelForge to Kiln.** The brand shifts from a generic "forge" metaphor to the sharper image of a kiln: a focused chamber where raw clay becomes a finished, premium object. One syllable, more distinctive in the creator-tools space, pairs naturally with the existing mauve-gradient vertical chamber icon.
- Entry point is now `python kiln.py` (was `python reelforge.py`). PyInstaller output binaries are `Kiln.exe` / `Kiln.app` / `Kiln`.
- `QSettings` organization key moved to `Kiln` with a one-time fallback read from the old `ReelForge` key so existing users keep their theme preference.
- Qt app property keys renamed (`reelforgeThemeId` → `kilnThemeId`, same for `reelforgeThemePreference`).
- README, CHANGELOG, architecture tree, logo prompts, wordmark SVG, and all user-visible strings updated to the new name. Titlebar brand label reads **Kiln**; subtitle reads "The kiln for vertical video."
- Cache / sidecar paths renamed (`.reelforge/` → `.kiln/`, `*.reelforge.srt` → `*.kiln.srt`).

### Verified
- App boots under every theme with the new brand mark, 6 sidebar tabs intact.
- End-to-end encode (NVENC + Center + adjustments + 2 overlays) still produces a clean MP4.
- No stale "ReelForge" / "reelforge" references remain in source or docs.

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
