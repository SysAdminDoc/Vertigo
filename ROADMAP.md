# Vertigo — Roadmap

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

- [ ] Hardware-encoder auto-detect across **4 backends** (NVENC / QSV /
  AMF / VideoToolbox). Autocrop-vertical has 2; openshorts has 0.

- [ ] PyQt6 batch queue + trim timeline + colour grading + text overlay
  editor — all competitors are CLI or web.

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
