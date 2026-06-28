# Research - Vertigo

## Executive Summary
Vertigo is a local-first PyQt6/FFmpeg studio for turning source footage into polished 9:16 clips with fast expression-driven reframing, hardware encoders, strong caption styling, batch export, trim helpers, and opt-in integrations. The strongest current shape is "desktop creator workbench," not cloud clipping automation: keep the local, no-telemetry charter and deepen trust, recovery, platform correctness, and guided optional integrations. Top opportunities: (1) harden media-ingest security against current FFmpeg/Pillow advisories, (2) add platform safe-zone overlays and validation, (3) preserve batch/export state with resumable job manifests, (4) expose optional integration readiness for pyannote and Pexels without bundling credentials, (5) add caption timing review and nudge tools, (6) refresh local packaging/release workflow after workflow removal, (7) add an accessibility test harness, and (8) keep cloud schedulers, team workspaces, and LLM virality scoring rejected.

## Product Map
- Core workflows: import local clips; pick platform preset and reframe mode; preview/trim with segment, highlight, silence, and speech helpers; generate/burn captions and overlays; export one clip or a queue.
- User personas: solo short-form creator; editor repurposing podcasts/interviews; technical creator who values local processing; power user willing to install optional models.
- Platforms and distribution: Python 3.10+ source run, PyInstaller single-file binaries for Windows/macOS/Linux, FFmpeg/ffprobe on PATH, MIT license.
- Key integrations and data flows: FFmpeg/ffprobe for media IO; OpenCV/MediaPipe/PySceneDetect/scipy for tracking and scenes; faster-whisper for captions; optional Silero VAD, auto-editor, Lighthouse, pycaps, BoxMOT, pyannote, Pexels/OpenCLIP, Katna.

## Competitive Landscape
- OpusClip / Klap / Vizard: strongest at multi-clip generation, branded captions, auto reframe, b-roll, social scheduling, and team/API workflows. Vertigo should learn safe-zone validation, review queues, batch clip variants, and optional b-roll review; avoid cloud upload dependency, credit meters, workspace lock-in, and scheduler credentials.
- Submagic: strong one-pass caption, b-roll, zoom, sound, and silence-cut automation. Vertigo should learn "review before apply" b-roll and dynamic edit controls; avoid opaque automatic edits that users cannot inspect locally.
- Adobe Premiere Pro Auto Reframe: strong sequence duplication, target aspect presets, and motion-speed tracking options. Vertigo should learn multi-preset export and explicit tracking-speed/motion controls; avoid becoming a general NLE.
- AI-Youtube-Shorts-Generator / OpenShorts / clippyme: strong OSS signal for long-form-to-shorts automation and active-speaker reframing. Vertigo should learn resumable jobs, metadata durability, and active-speaker optional paths; avoid their recurring cloud/LLM/API fragility and subtitle rendering failures.
- Autocrop-vertical / Auto Vertical Reframe: strong scene-level person detection, TRACK vs LETTERBOX decisions, and virtual camera optimization. Vertigo already beats them in UI and hardware encoding; learn person/body fallback for non-frontal footage, but keep it optional to avoid heavy default YOLO/SAM dependencies.
- Google AutoFlip / RetargetVid / SAM 2: useful architecture references for saliency, scene isolation, object tracking, and temporal smoothness. Vertigo should borrow the concept of saliency-aware fallback and manual object prompt experiments; avoid default heavyweight segmentation stacks until there is a clear local model packaging path.

## Security, Privacy, and Reliability
- Verified: `requirements.txt` allows `Pillow>=10.3.0`, while Pillow advisories in 2026 affect `>=10.3.0,<12.1.1` and PDF hangs before `12.2.0`; because Vertigo uses Pillow for assets/keyframes, the floor should be raised and tested.
- Verified: Vertigo shells user-supplied media through FFmpeg in `core/probe.py`, `core/encode.py`, `core/highlights.py`, `core/hook_score.py`, and `core/vad.py`; FFmpeg has 2026 advisories including MagicYUV RCE before 8.1.2. Add version detection and warning/preflight gates for stale FFmpeg.
- Verified: `README.md` still describes `.github/workflows/build.yml` and CI release uploads, but `.github/` is absent and recent git history removed workflows. Packaging docs and release checks need local-build truth.
- Verified: existing `ROADMAP.md` R10 is still the correct worker-output scrub task; local scan shows `SubtitleWorker`, `HighlightsWorker`, and `AutoEditWorker` lack the explicit partial-output cleanup parity present in `EncodeWorker` and `PycapsWorker`.
- Likely: batch queue state is in memory (`ui/batch_queue.py`, `ui/main_controller.py`), so a crash or close during a long queue loses pending work and candidate decisions. A local job manifest would improve recovery without adding cloud state.
- Missing guardrails: platform safe-zone preview/validation, stale dependency warning, resumable batch manifests, credential readiness checks for HF/Pexels, and user-visible export environment diagnostics.

## Architecture Assessment
- `ui/main_controller.py` is the right orchestration boundary but remains a high-churn module; new recovery, integration-readiness, and export-matrix work should add small core helpers first and keep controller code as signal wiring.
- `core.broll` and `core.diarize` are importable but mostly hidden from the GUI. Add an optional integration readiness panel before adding direct automation, so users see missing dependency, credential, model/license, and offline fallback state.
- `ui/video_player.py` and `core/presets.py` should own platform safe-zone metadata so preview, captions, overlays, and acceptance tests all share one source of truth.
- Caption quality is strong, but Whisper word timing is an inference-time approximation and can drift around pauses; `ui/subtitles_panel.py` needs a local caption review/nudge surface before more caption styles are added.
- Tests are broad for unit-level media logic and smoke UI, but missing coverage for accessibility naming/focus order, local packaging sanity, dependency-version checks, and crash-resume behavior.
- Coverage note: security, accessibility, observability, testing, docs, distribution, offline resilience, optional integrations, migration, and upgrade strategy are covered by the recommendations above; i18n/l10n is limited to existing caption-language support for now; mobile and multi-user are rejected below to preserve the desktop local-only charter.

## Rejected Ideas
- LLM virality scoring from AI-Youtube-Shorts-Generator, OpenShorts, OpusClip, and Klap: rejected because Vertigo's charter says no LLM ranking and local deterministic segment proposals are already the preferred lane.
- Direct social scheduling from Vizard/OpenShorts/clippyme: rejected because it introduces account credentials, platform API churn, and cloud-sync behavior that conflicts with the local-only charter.
- Team workspace/API productization from OpusClip/Vizard: rejected because Vertigo is a desktop workbench, not a hosted collaboration service.
- Full general NLE timeline from Premiere/CapCut: rejected because it dilutes the focused 9:16 repurposing workflow.
- Default YOLO/SAM 2 segmentation stack from Autocrop-vertical, Auto Vertical Reframe, and SAM 2: rejected as a default dependency because model weight size and packaging complexity outweigh value for normal talking-head clips; keep as a later optional experiment.
- Mobile app parity from Vizard/CapCut: rejected for this cycle because the desktop pipeline, binary packaging, and local reliability have higher leverage.

## Sources
OSS competitors:
- https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator
- https://samuraigpt-ai-youtube-shorts-generator-34.mintlify.app/
- https://github.com/mutonby/openshorts
- https://mutonby-openshorts.mintlify.app/introduction
- https://github.com/mutonby/openshorts/issues
- https://github.com/kamilstanuch/Autocrop-vertical
- https://github.com/KazKozDev/auto-vertical-reframe
- https://github.com/cipher-vault-hq/awesome-free-opusclip-alternatives

Commercial and platform:
- https://www.opus.pro/
- https://www.opus.pro/api
- https://klap.app/
- https://vizard.ai/
- https://docs.vizard.ai/docs/publish-clips-to-social-media
- https://www.submagic.co/features/auto-video-editor
- https://www.submagic.co/features/b-roll
- https://helpx.adobe.com/premiere/desktop/add-video-effects/commonly-used-effects/add-auto-reframe-effect-to-a-sequence.html
- https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads
- https://www.facebook.com/business/help/980593475366490
- https://support.google.com/google-ads/answer/13547298

Research, dependencies, and security:
- https://opensource.googleblog.com/2020/02/
- https://github.com/bmezaris/RetargetVid/blob/main/README.md
- https://aclanthology.org/J97-1003.pdf
- https://ai.meta.com/research/sam2/
- https://pypi.org/project/PyQt6/
- https://pypi.org/project/mediapipe/
- https://pyinstaller.org/en/stable/CHANGES.html
- https://ffmpeg.org/security.html
- https://github.com/advisories/GHSA-qff7-4q6c-m8h6
- https://github.com/python-pillow/Pillow/security/advisories/GHSA-cfh3-3jmp-rvhc
- https://nvd.nist.gov/vuln/detail/CVE-2026-42310

## Open Questions
None blocking.
