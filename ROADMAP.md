# Vertigo — Roadmap

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

- [ ] Hardware-encoder auto-detect across **4 backends** (NVENC / QSV /
  AMF / VideoToolbox). Autocrop-vertical has 2; openshorts has 0.

- [ ] PyQt6 batch queue + trim timeline + colour grading + text overlay
  editor — all competitors are CLI or web.

- [ ] P1 - Add optional integration readiness panel
  Why: `core.diarize` and `core.broll` are importable but hidden behind HF/Pexels/model prerequisites, while commercial tools make b-roll, speaker-aware edits, and captions obvious product surfaces.
  Evidence: OpusClip API/features; Submagic b-roll; Vizard features; pyannote speaker-diarization model card; `core/diarize.py`; `core/broll.py`; existing ROADMAP T4b and b-roll partial items.
  Touches: `ui/main_window.py`, `ui/main_controller.py`, `ui/subtitles_panel.py` or new non-markdown UI module, `core/diarize.py`, `core/broll.py`, `requirements-optional.txt`, `tests/`.
  Acceptance: UI lists each optional integration with installed/missing/credential/license state, lets users validate HF_TOKEN and PEXELS_API_KEY without storing secrets, and routes users to existing local fallbacks when unavailable.
  Complexity: M

- [ ] P1 - Add caption timing review and nudge tools
  Why: faster-whisper supports word timestamps, but Whisper word timing is approximate around pauses; creators need a local way to correct visible caption drift before burn-in.
  Evidence: faster-whisper README; Whisper word-timestamp discussion; OpenShorts subtitle-rendering issue; `core/subtitles.py`; `ui/subtitles_panel.py`.
  Touches: `core/subtitles.py`, `core/caption_types.py`, `ui/subtitles_panel.py`, `ui/video_player.py`, `ui/main_controller.py`, `tests/`.
  Acceptance: After transcription, users can preview caption chunks, shift selected/all captions by small offsets, split/merge simple chunks, save the adjusted sidecar, and export uses the adjusted timing.
  Complexity: L

- [ ] P2 - Add local multi-preset export matrix
  Why: Premiere Auto Reframe duplicates sequences for target ratios and commercial clippers produce variants per platform; Vertigo has presets but exports one active geometry at a time.
  Evidence: Adobe Auto Reframe docs; OpusClip API; Klap AI Reframe 2; `core/presets.py`; `ui/main_controller.py`.
  Touches: `core/presets.py`, `core/encode.py`, `ui/output_panel.py`, `ui/main_controller.py`, `ui/batch_queue.py`, `tests/`.
  Acceptance: Users can select multiple local presets for a clip or queue, Vertigo writes clear per-platform filenames, progress groups child exports under the source entry, and failures isolate to that preset.
  Complexity: L

- [ ] P2 - Refresh local packaging and release sanity checks
  Why: `.github/` workflows were removed but README still describes CI release uploads, and PyInstaller/PyQt/OpenCV/MediaPipe releases have moved since the current docs and dependency floors.
  Evidence: `git log -10`; `README.md`; `vertigo.spec`; PyInstaller changelog; PyQt6/PyQt6-Qt6 PyPI; opencv-python PyPI; mediapipe PyPI.
  Touches: `README.md`, `CHANGELOG.md`, `vertigo.spec`, `requirements.txt`, local release scripts or non-markdown checklist, `tests/`.
  Acceptance: Docs describe local-only builds, a local sanity command verifies PyInstaller spec version/assets/hidden imports, and a fresh artifact build no longer depends on GitHub Actions.
  Complexity: M

- [ ] P2 - Add accessibility coverage for the full PyQt surface
  Why: Vertigo has accessible names on many controls, but there is no test that every interactive control in the current workspace has a usable accessible name, focus policy, and reduced-motion behavior.
  Evidence: `ui/video_player.py`; `ui/subtitles_panel.py`; `ui/output_panel.py`; `ui/titlebar.py`; `tests/test_theme_tokens.py`; `tests/test_main_window_smoke.py`.
  Touches: `ui/`, `tests/test_main_window_smoke.py`, `tests/test_theme_tokens.py`.
  Acceptance: A UI smoke test walks buttons, sliders, comboboxes, checkboxes, and custom widgets; failures identify missing accessible names/descriptions or broken focus policies; reduced-motion opt-out remains covered.
  Complexity: S

- [ ] P3 - Prototype optional object/body tracking fallback
  Why: Face-only tracking misses non-frontal, gameplay, product, sports, or full-body footage where competitors use YOLO/person detection or saliency/object segmentation.
  Evidence: Autocrop-vertical; Auto Vertical Reframe; Google AutoFlip; SAM 2; `core/detect.py`; `core/tracker_boxmot.py`; `core/reframe.py`.
  Touches: `core/detect.py`, `core/tracker_boxmot.py`, optional dependency gate, `ui/main_controller.py`, `tests/`.
  Acceptance: Behind an opt-in toggle, Vertigo can follow a person/object fallback when no face track is found, falls back cleanly without model weights, and never changes the default lightweight path.
  Complexity: XL
