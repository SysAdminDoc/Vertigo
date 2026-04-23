<div align="center">

<img src="assets/icon.png" alt="ReelForge" width="140"/>

# ReelForge

**Premium vertical-video forge for YouTube Shorts, TikTok & Instagram Reels.**

![version](https://img.shields.io/badge/version-0.4.0-cba6f7?style=for-the-badge)
![license](https://img.shields.io/badge/license-MIT-a6e3a1?style=for-the-badge)
![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-89b4fa?style=for-the-badge)
![python](https://img.shields.io/badge/python-3.10%2B-f9e2af?style=for-the-badge)

Drop any horizontal video. Get a polished 9:16 vertical with AI-tracked framing.

</div>

---

## Features

- **Premium PyQt6 UI** — polished System / Mocha / Graphite / Latte themes, frameless custom titlebar, calm editor surfaces, refined focus states, accessible controls, and polished feedback.
- **Four reframe modes:**
  - **Center Crop** — static center column, zero analysis.
  - **Smart Track** — MediaPipe face detection; viewport pans to follow subjects over time with smoothed, *scene-aware* keyframes that never cross a hard cut.
  - **Blur Letterbox** — full source frame on a softly blurred, zoomed backdrop.
  - **Manual** — drag the viewport on the live preview to lock any column.
- **Platform presets** — YouTube Shorts, TikTok, Instagram Reels, Square (1:1). One click switches output geometry and encoder target bitrate.
- **Batch queue** — drop many clips at once, preview any one, then **Export All** to a folder. Per-item status indicator (pending / active / done / failed).
- **Trim timeline** — dual-thumb in/out range slider directly on the preview. Exports respect the trim window via FFmpeg `-ss` / `-t`.
- **Adjustments panel** — live brightness / contrast / saturation sliders; applied via FFmpeg `eq=` filter appended to the reframe chain.
- **Scene detection** — PySceneDetect (with a histogram-delta fallback) segments the timeline to stabilize Smart Track.
- **Hardware encoding** — auto-detects NVIDIA NVENC, Intel QuickSync, AMD AMF, Apple VideoToolbox, and the libx264/libx265 CPU encoders. Pick one in the Output tab, drive a single quality slider, tune the speed preset.
- **AI captions** — optional faster-whisper transcription (opt-in lazy install) with SRT burn-in. Word-wrapped, mobile-safe styling baked directly into the exported pixels.
- **Text overlays** — title cards, top straps, lower-thirds, and bottom captions. Per-overlay time range, color, and font size. Preset library for common Shorts/Reels motifs. All burned into the output via `drawtext=` filter chain.
- **Live crop viewport** overlaid on the preview player so you see the target frame before rendering.
- **Async FFmpeg encoding** with real-time progress bar and a scrolling log panel.
- **Turnkey bootstrap** — single-command launch, auto-installs missing Python deps on first run.
- **Binary builds** — `pyinstaller --clean reelforge.spec` produces single-file Windows, macOS `.app`, and Linux exes. GitHub Actions workflow builds all three on every tag push (or `workflow_dispatch`) and uploads to a draft release via `gh release upload --clobber`.

## Install

```bash
git clone https://github.com/SysAdminDoc/ReelForge.git
cd ReelForge
python reelforge.py
```

First run bootstraps PyQt6, OpenCV, NumPy, Pillow, MediaPipe, and `ffmpeg-python`. You must also have **FFmpeg** on `PATH`:

```bash
# Windows
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

## Use

1. Launch `python reelforge.py`.
2. Drop a video on the preview area (or click to browse).
3. Pick a platform preset (Shorts / TikTok / Reels / Square).
4. Pick a reframe mode. For Smart Track, MediaPipe scans the clip and returns tracking keyframes.
5. Click **Export Vertical** and choose an output path. Progress streams in the log panel.

## Architecture

```
reelforge.py              entry + dependency bootstrap
reelforge.spec            PyInstaller build spec (single-file, per-OS icon)
.github/workflows/build.yml  Multi-OS CI + GitHub Release upload
core/
  probe.py                ffprobe wrapper (VideoInfo dataclass)
  presets.py              platform output presets (Shorts/TikTok/Reels/Square)
  detect.py               MediaPipe face tracker (Haar fallback)
  scenes.py               scene detection (PySceneDetect + histogram fallback)
  encoders.py             hardware encoder detection (NVENC/QSV/AMF/VT + CPU)
  subtitles.py            faster-whisper wrapper (lazy install) + SRT writer
  overlays.py             TextOverlay dataclass + drawtext filter chain
  reframe.py              FFmpeg filter graph per mode + Adjustments dataclass
  encode.py               FFmpeg subprocess + progress parsing + trim + burn-in
ui/
  theme.py                semantic theme tokens + QSS stylesheet generation
  titlebar.py             frameless draggable titlebar + theme picker + brand mark
  assets.py               bundle-aware asset resolver (source + PyInstaller)
  widgets.py              GlassPanel, ModeCard, Toast
  file_drop.py            multi-file drag-drop import zone
  range_slider.py         dual-thumb trim slider + playhead marker
  video_player.py         QMediaPlayer preview + crop-viewport overlay + trim
  batch_queue.py          queue panel with per-item status
  adjustments_panel.py    brightness / contrast / saturation sliders
  output_panel.py         encoder / quality / speed controls
  subtitles_panel.py      AI caption generation + burn-in toggle
  overlays_panel.py       text-overlay editor (titles / lower-thirds)
  main_window.py          composition + wiring + batch driver
workers/
  detect_worker.py        QThread: runs FaceTracker
  encode_worker.py        QThread: runs encode.run()
  subtitle_worker.py      QThread: runs faster-whisper transcription
assets/
  icon.svg / icon.png / icon.ico + size variants (16/32/48/128/256/512)
  wordmark.svg           typography-focused brand wordmark
  build_icons.py         procedural Pillow renderer (SVG + PNG + ICO)
  logo_prompts.md        5 AI image prompts for high-end brand generation
```

## Reframe strategy reference

| Mode | FFmpeg summary | When to use |
| --- | --- | --- |
| Center | `crop,scale` static | Subject always centered |
| Smart Track | `crop=...:x=<piecewise lerp>,scale` | Talking heads, walking subjects |
| Blur Letterbox | `split, blur+crop bg, scale fg, overlay` | Preserve full frame, no loss |
| Manual | `crop` with locked offset | You want total control |

## Build binaries

```bash
pip install pyinstaller
pyinstaller --clean reelforge.spec
# dist/ReelForge.exe  (Windows)
# dist/ReelForge.app  (macOS)
# dist/ReelForge      (Linux)
```

Or push a tag and let CI build all three — see `.github/workflows/build.yml`. A `workflow_dispatch` run with a tag input lands three artifacts on a draft release.

## Requirements

- Python 3.10+
- FFmpeg / ffprobe on PATH
- PyQt6, OpenCV, MediaPipe, NumPy, Pillow, PySceneDetect (auto-installed)

## License

MIT — see [LICENSE](LICENSE).
