"""Vertigo main-window controller — worker lifecycle and batch driver.

The controller owns every background job (detect / encode / transcribe /
scene-detect) together with the state those jobs produce or consume:

    workers         detect_worker, encode_worker, subtitle_worker,
                    scene_worker — the live QThread handles
    analysis        track_points, scenes, clip_subs — output from
                    DetectWorker / SceneWorker / SubtitleWorker that
                    later runs want to read
    batch           batch_running, batch_out_dir, suppress_auto_detect —
                    flags the batch driver flips
    export          last_output_path — the most recent export, used
                    when the user asks to "reveal export"

``MainWindow`` keeps everything that is genuinely UI-session state —
the loaded clip, the selected preset / mode / trim / overlays / output
choice — plus every widget and every refresh helper. The controller
reaches into the window for widget access (``self.win._toast``,
``self.win._detect_progress``, …) and for refresh helpers
(``self.win._refresh_overview``). This is deliberate coupling: the two
classes are designed together and live in the same package.

Public API (called from ``main_window._wire`` / panel signals / window
helpers):

    controller.run_transcribe(...)
    controller.on_subs_cleared()
    controller.run_detect()
    controller.start_export()
    controller.start_batch_export()
    controller.run_dry()
    controller.cancel_active()
    controller.open_last_output_folder()
    controller.kick_scene_detection(path)
    controller.shutdown(timeout_ms)
    controller.has_running_worker()

Everything else on this class starts with ``_`` and is an internal
detail (worker-signal handlers, dialog helpers, batch step).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontMetrics
from PyQt6.QtWidgets import QMenu, QMessageBox

from core.encode import EncodeJob
from core.probe import VideoInfo, probe
from core.reframe import ReframeMode, build_plan
from core.subtitles import is_installed as subtitles_installed
from workers.detect_worker import DetectWorker
from workers.encode_worker import EncodeWorker
from workers.scene_worker import SceneWorker
from workers.subtitle_worker import SubtitleWorker
from workers.auto_edit_worker import AutoEditWorker
from workers.highlights_worker import HighlightsWorker
from workers.vad_worker import VadWorker

from .batch_queue import QueueEntry, QueueStatus

if TYPE_CHECKING:
    from .main_window import MainWindow


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class MainController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.win = window

        # worker handles
        self.detect_worker: DetectWorker | None = None
        self.encode_worker: EncodeWorker | None = None
        self.subtitle_worker: SubtitleWorker | None = None
        self.scene_worker: SceneWorker | None = None
        self.vad_worker: VadWorker | None = None
        self.highlights_worker: HighlightsWorker | None = None
        self.auto_edit_worker: AutoEditWorker | None = None

        # analysis results (consumed by export and UI refreshers)
        self.track_points: list = []
        self.scenes: list[tuple[float, float]] = []
        self.clip_subs: dict[int, Path] = {}

        # batch driver state
        self.batch_running: bool = False
        self.batch_out_dir: Path | None = None
        self.suppress_auto_detect: bool = False

        # export output tracking
        self.last_output_path: Path | None = None

    # --------------------------------------------------------------- wiring
    def wire(self) -> None:
        """Route the top-level hero / player / drop-zone signals.

        Signals emitted by widgets that are built inside the per-panel
        ``_build_*`` helpers (detect button, dry-run button, subtitles
        panel, open-output button) are still connected where the widgets
        are constructed — those are local concerns and moving them up
        here would force every build helper to expose another accessor.
        What this method handles is the chrome-level surfaces that are
        referenced by name on MainWindow.
        """
        w = self.win
        w._drop.file_dropped.connect(w._import_one)
        w._drop.files_dropped.connect(w._import_many)
        w._browse_btn.clicked.connect(w._browse_for_clips)
        w._hero_output_btn.clicked.connect(self.open_last_output_folder)
        w._export_btn.clicked.connect(self.start_export)
        w._export_all_btn.clicked.connect(self.start_batch_export)
        w._cancel_btn.clicked.connect(self.cancel_active)
        w._player.canvas.viewport_dragged.connect(w._on_manual_drag)
        w._player.position_changed.connect(w._sync_track_pos)
        w._player.trim_changed.connect(w._on_trim_changed)
        w._player.tighten_btn.clicked.connect(self.run_tighten_silences)
        w._player.highlights_btn.clicked.connect(self.run_find_highlights)
        w._player.trim_silences_btn.clicked.connect(self.run_trim_silences)
        w._export_thumbs_btn.clicked.connect(self.export_thumbnails)

    # --------------------------------------------------------------- status
    def has_running_worker(self) -> bool:
        for w in (
            self.detect_worker,
            self.encode_worker,
            self.subtitle_worker,
            self.vad_worker,
            self.highlights_worker,
            self.auto_edit_worker,
        ):
            if w is not None and w.isRunning():
                return True
        return False

    def shutdown(self, timeout_ms: int = 1500) -> None:
        """Cancel every in-flight worker and join for up to ``timeout_ms``.

        Called from MainWindow.closeEvent so the GUI process can exit
        cleanly even when a long-running encode or transcribe is in
        flight. Scene detection is fire-and-forget and is not cancelled
        by cancel_active(), so we stop it here explicitly. Workers that
        fail to finish within the timeout are surfaced on stderr so a
        packaging build leaves breadcrumbs in ``crash.log``.
        """
        import sys

        self.cancel_active()
        if self.scene_worker is not None and self.scene_worker.isRunning():
            self.scene_worker.cancel()
        for worker in (
            self.encode_worker,
            self.detect_worker,
            self.subtitle_worker,
            self.scene_worker,
            self.vad_worker,
            self.highlights_worker,
            self.auto_edit_worker,
        ):
            if worker is None or not worker.isRunning():
                continue
            if not worker.wait(timeout_ms):
                try:
                    print(
                        f"[Vertigo] Warning: {type(worker).__name__} did not "
                        f"finish within {timeout_ms}ms on shutdown",
                        file=sys.stderr,
                    )
                except Exception:
                    pass

    def drop_clip_subs(self, entry_id: int) -> None:
        """Release per-clip subtitle state for a removed queue entry.

        The transcribe worker writes an auto-generated SRT/ASS into the
        clip's parent directory; when the user removes the clip from the
        queue we should delete that file and forget the mapping to avoid
        leaking disk state across sessions.
        """
        path = self.clip_subs.pop(entry_id, None)
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    # --------------------------------------------------------------- captions
    def on_subs_cleared(self) -> None:
        current = self.win._current_entry
        if current and current.id in self.clip_subs:
            path = self.clip_subs.pop(current.id)
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        self.win._refresh_overview()

    def run_transcribe(
        self,
        model: str,
        language: str | None,
        preset_id: str = "pop",
        face_aware: bool = False,
    ) -> None:
        w = self.win
        if not w._info or not w._current_entry:
            w._toast.show_toast("Load a clip first.", kind="warning")
            return
        if self.subtitle_worker and self.subtitle_worker.isRunning():
            return

        from core.caption_styles import resolve as resolve_caption_preset
        preset = resolve_caption_preset(preset_id)

        is_letterbox = w._mode is ReframeMode.BLUR_LETTERBOX

        out_dir = w._info.path.parent
        w._subs_panel.set_running(True)
        face_note = "  \u00b7  face-aware" if face_aware and not is_letterbox else ""
        w._subs_panel.set_status(
            f"Transcribing {w._info.path.name} with whisper-{model} \u2014 {preset.label} style{face_note}"
        )
        if not subtitles_installed():
            w._subs_panel.set_status("Installing faster-whisper (one-time, ~200 MB)\u2026")
        w._refresh_overview()

        entry_id = w._current_entry.id
        self.subtitle_worker = SubtitleWorker(
            w._info.path,
            out_dir,
            preset=preset,
            height_px=w._preset.height,
            model_name=model,
            language=language,
            face_aware=face_aware,
            letterbox=is_letterbox,
        )
        self.subtitle_worker.progress.connect(w._subs_panel.set_progress)
        self.subtitle_worker.status.connect(w._subs_panel.set_status)
        self.subtitle_worker.finished_ok.connect(
            lambda srt, eid=entry_id: self._on_subs_done(srt, eid)
        )
        self.subtitle_worker.failed.connect(self._on_subs_fail)
        self.subtitle_worker.start()

    def _on_subs_done(self, srt_str: str, entry_id: int) -> None:
        srt = Path(srt_str)
        self.clip_subs[entry_id] = srt
        w = self.win
        w._subs_panel.set_running(False)
        if w._current_entry and w._current_entry.id == entry_id:
            w._subs_panel.set_srt_path(srt)
        w._toast.show_toast(f"Captions ready: {srt.name}", kind="success")
        w._refresh_overview()

    def _on_subs_fail(self, msg: str) -> None:
        w = self.win
        w._subs_panel.set_running(False)
        w._subs_panel.set_status(f"Transcription failed: {msg}", tone="warning")
        w._toast.show_toast(msg, kind="error")
        w._refresh_overview()

    # --------------------------------------------------------------- thumbnails
    def export_thumbnails(self) -> None:
        """Write six representative thumbnails (PNG) from the loaded
        clip to a user-chosen folder.

        Uses ``core.keyframes`` — Katna when installed, evenly-spaced
        cv2 frames as the always-available fallback. The call runs on
        the GUI thread because the cv2 path is fast (<1 s for six
        frames on a 1080p clip); if Katna is installed and users hit
        long clips we can lift this onto a worker later.
        """
        from core import keyframes
        from .file_dialogs import get_existing_directory

        w = self.win
        if not w._info:
            w._toast.show_toast("Load a clip first.", kind="warning")
            return
        out_dir = get_existing_directory(w, "Folder for thumbnails")
        if not out_dir:
            return
        try:
            written = keyframes.save_thumbnails(
                w._info.path,
                Path(out_dir),
                n=6,
                prefix=w._info.path.stem,
            )
        except Exception as e:
            w._toast.show_toast(f"Thumbnail export failed: {e}", kind="error")
            return
        if not written:
            w._toast.show_toast(
                "Couldn't decode any frames from this clip.",
                kind="warning",
            )
            return
        w._toast.show_toast(
            f"Saved {len(written)} thumbnail{'' if len(written) == 1 else 's'}",
            kind="success",
        )

    # --------------------------------------------------------------- tighten
    def run_tighten_silences(self) -> None:
        """Run Silero VAD and pull the trim handles to the outer
        speech edges. Surfaces install/setup problems via toast so
        users know why the button did nothing.
        """
        from core import vad

        w = self.win
        if not w._info:
            w._toast.show_toast("Load a clip first.", kind="warning")
            return
        if self.vad_worker and self.vad_worker.isRunning():
            return
        if not vad.is_available():
            w._toast.show_toast(
                "Install silero-vad to enable speech tightening:"
                "  pip install silero-vad",
                kind="warning",
                duration_ms=4500,
            )
            return

        w._toast.show_toast("Analysing speech\u2026", kind="info")
        w._player.tighten_btn.setEnabled(False)

        worker = VadWorker(
            video_path=w._info.path,
            duration_sec=w._info.duration,
        )
        worker.trim_ready.connect(self._on_tighten_ready)
        worker.failed.connect(self._on_tighten_failed)
        self.vad_worker = worker
        worker.start()

    def _on_tighten_ready(self, low: float, high: float, coverage: float) -> None:
        w = self.win
        w._player.set_trim_range(low, high)
        # _on_trim_changed fires from the scrubber already; we still
        # update window trim state directly so plan / refresh helpers
        # see the new values immediately.
        w._trim_low = low
        w._trim_high = high
        w._refresh_platform_notice()
        w._refresh_overview()
        pct = int(round(coverage * 100))
        w._toast.show_toast(
            f"Trimmed to speech \u00b7 {pct}% of the clip is voice",
            kind="success",
        )
        w._player.tighten_btn.setEnabled(True)

    def _on_tighten_failed(self, msg: str) -> None:
        w = self.win
        w._player.tighten_btn.setEnabled(True)
        if msg == "Cancelled.":
            return
        w._toast.show_toast(msg, kind="warning")

    # --------------------------------------------------------------- highlights
    def run_find_highlights(self) -> None:
        """Score the clip for high-energy moments and pop a menu the
        user can pick from to drop the trim on the chosen span.

        Uses ``core.highlights.score_spans`` which transparently chooses
        Lighthouse (when installed) or a fallback sliding-window audio
        energy sweep. Either path runs on ``HighlightsWorker``.
        """
        w = self.win
        if not w._info:
            w._toast.show_toast("Load a clip first.", kind="warning")
            return
        if self.highlights_worker and self.highlights_worker.isRunning():
            return

        w._toast.show_toast("Scanning for highlights\u2026", kind="info")
        w._player.highlights_btn.setEnabled(False)

        worker = HighlightsWorker(video_path=w._info.path, top_n=5)
        worker.finished_ok.connect(self._on_highlights_ready)
        worker.failed.connect(self._on_highlights_failed)
        self.highlights_worker = worker
        worker.start()

    def _on_highlights_ready(self, highlights: list) -> None:
        w = self.win
        w._player.highlights_btn.setEnabled(True)
        if not highlights:
            w._toast.show_toast(
                "No clear highlights detected in this clip.",
                kind="warning",
            )
            return
        self._present_highlights_menu(highlights)

    def _on_highlights_failed(self, msg: str) -> None:
        w = self.win
        w._player.highlights_btn.setEnabled(True)
        if msg == "Cancelled.":
            return
        w._toast.show_toast(msg, kind="warning")

    def _present_highlights_menu(self, highlights: list) -> None:
        """Show a popup menu of ranked highlights anchored to the
        Find-highlights button. Clicking an entry drops the trim.

        Highlights are already sorted best-score-first by the
        controller; we display them that way but keep the timeline
        position in the label so users can see where they are.
        """
        w = self.win
        menu = QMenu(w)
        menu.setAccessibleName("Highlight moments")

        for h in highlights:
            label = self._format_highlight_label(h)
            action = menu.addAction(label)
            # Capture start/end per-action; lambdas in a loop would bind
            # to the last value otherwise.
            action.triggered.connect(
                lambda _checked=False, s=float(h.start), e=float(h.end):
                    self._apply_highlight_trim(s, e)
            )

        # Anchor the menu below the button that triggered it.
        btn = w._player.highlights_btn
        global_pos = btn.mapToGlobal(btn.rect().bottomLeft())
        menu.exec(global_pos)

    def _format_highlight_label(self, h) -> str:
        score_pct = int(round(max(0.0, min(1.0, float(h.score))) * 100))
        return (
            f"{_fmt_duration(max(0.0, float(h.start)))} \u2013 "
            f"{_fmt_duration(max(0.0, float(h.end)))}"
            f"   \u00b7   {score_pct}%   [{h.source}]"
        )

    def _apply_highlight_trim(self, start: float, end: float) -> None:
        w = self.win
        w._player.set_trim_range(start, end)
        w._trim_low = start
        w._trim_high = end
        w._refresh_platform_notice()
        w._refresh_overview()

    # --------------------------------------------------------------- trim silences
    def run_trim_silences(self) -> None:
        """Kick auto-editor and let the user pick a speech-contiguous
        span to trim to. The output set is ranked by duration so the
        longest continuous speech section shows up first.
        """
        from core import auto_edit

        w = self.win
        if not w._info:
            w._toast.show_toast("Load a clip first.", kind="warning")
            return
        if self.auto_edit_worker and self.auto_edit_worker.isRunning():
            return
        if not auto_edit.is_available():
            w._toast.show_toast(
                f"auto-editor not found on PATH. Install with: "
                f"{auto_edit.install_hint()}",
                kind="warning",
                duration_ms=5000,
            )
            return

        w._toast.show_toast("Scanning for silences\u2026", kind="info")
        w._player.trim_silences_btn.setEnabled(False)

        worker = AutoEditWorker(video_path=w._info.path)
        worker.finished_ok.connect(self._on_trim_silences_ready)
        worker.failed.connect(self._on_trim_silences_failed)
        self.auto_edit_worker = worker
        worker.start()

    def _on_trim_silences_ready(self, spans: list) -> None:
        w = self.win
        w._player.trim_silences_btn.setEnabled(True)
        if not spans:
            w._toast.show_toast(
                "Nothing to trim — no speech sections detected.",
                kind="warning",
            )
            return
        # Sort by duration descending; show the top 5 so the menu
        # stays legible on small displays. Ties are broken by the
        # earlier start time so the clip's opening beat wins.
        spans_ranked = sorted(
            spans, key=lambda s: (-s.duration, s.start)
        )[:5]
        self._present_trim_silence_menu(spans_ranked)

    def _on_trim_silences_failed(self, msg: str) -> None:
        w = self.win
        w._player.trim_silences_btn.setEnabled(True)
        if msg == "Cancelled.":
            return
        w._toast.show_toast(msg, kind="warning")

    def _present_trim_silence_menu(self, spans: list) -> None:
        w = self.win
        menu = QMenu(w)
        menu.setAccessibleName("Speech sections")
        for span in spans:
            label = self._format_silence_label(span)
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, s=float(span.start), e=float(span.end):
                    self._apply_highlight_trim(s, e)
            )
        btn = w._player.trim_silences_btn
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _format_silence_label(self, span) -> str:
        return (
            f"{_fmt_duration(span.start)} \u2013 "
            f"{_fmt_duration(span.end)}"
            f"   \u00b7   {_fmt_duration(span.duration)} of speech"
        )

    # --------------------------------------------------------------- detection
    def run_detect(self) -> None:
        w = self.win
        if not w._info:
            w._toast.show_toast("Load a clip before running Smart Track.", kind="warning")
            w._refresh_detection_actions()
            return
        if self.detect_worker and self.detect_worker.isRunning():
            return
        w._set_detect_status("Scanning for faces\u2026", tone="accent")
        w._detect_progress.setValue(0)
        w._detect_progress.setFormat("Analysis %p%")
        w._detect_progress.show()
        w._refresh_detection_actions()

        if self.scenes:
            n = len(self.scenes)
            w._scene_label.setText(f"{n} scene{'' if n == 1 else 's'} detected \u00b7 panning will respect cuts")
        elif self.scene_worker and self.scene_worker.isRunning():
            w._scene_label.setText("Scene cuts are still loading in the background.")
        else:
            w._scene_label.setText("Continuous take \u2014 no hard cuts detected")

        self.detect_worker = DetectWorker(
            w._info.path,
            sample_fps=2.0,
            smoothing=0.65,
            crop_width_frac=self._smart_track_crop_width_frac(),
        )
        self.detect_worker.progress.connect(
            lambda v: w._detect_progress.setValue(int(v * 100))
        )
        self.detect_worker.finished_ok.connect(self._on_detect_done)
        self.detect_worker.failed.connect(self._on_detect_fail)
        self.detect_worker.start()
        w._refresh_detection_actions()
        w._refresh_overview()

    def _on_detect_done(self, points: list) -> None:
        w = self.win
        self.track_points = points
        w._detect_progress.hide()
        if not points:
            w._set_detect_status(
                "No faces detected \u2014 export will fall back to a stable center crop.",
                tone="warning",
            )
        else:
            extra = f" across {len(self.scenes)} scenes" if self.scenes else ""
            w._set_detect_status(
                f"Tracking {len(points)} keyframes{extra}. Export will follow the subject.",
                tone="success",
            )
        if points:
            w._player.set_track_x(points[0].x)
        w._refresh_detection_actions()
        w._refresh_overview()

    def _on_detect_fail(self, msg: str) -> None:
        w = self.win
        w._detect_progress.hide()
        w._set_detect_status(f"Detection failed: {msg}", tone="warning")
        w._toast.show_toast("Smart Track failed. Try Center Crop or Manual.", kind="error")
        w._refresh_detection_actions()
        w._refresh_overview()

    # --------------------------------------------------------------- export
    def start_export(self) -> None:
        w = self.win
        if not w._info or not w._current_entry:
            return
        if not self._confirm_platform_duration():
            return
        from .file_dialogs import get_save_video_path
        suggested = self._default_output_path(w._info)
        path = get_save_video_path(w, suggested)
        if not path:
            return
        self._run_encode_job(w._info, Path(path), w._current_entry)

    def _confirm_platform_duration(self) -> bool:
        w = self.win
        if not w._info or not w._preset.max_duration:
            return True
        duration = max(0.0, (w._trim_high or w._info.duration) - (w._trim_low or 0.0))
        if duration <= w._preset.max_duration:
            return True
        answer = QMessageBox.warning(
            w,
            "Export above platform limit?",
            (
                f"The current trim is {_fmt_duration(duration)}, which is longer than "
                f"the {w._preset.label} limit of {_fmt_duration(w._preset.max_duration)}.\n\n"
                "Export anyway?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_batch_platform_durations(self, entries: list[QueueEntry]) -> bool:
        w = self.win
        if not w._preset.max_duration:
            return True

        over_limit: list[str] = []
        for entry in entries:
            try:
                info = probe(entry.path)
            except Exception:
                continue
            if info.duration > w._preset.max_duration:
                over_limit.append(f"{entry.path.name} ({_fmt_duration(info.duration)})")

        if not over_limit:
            return True

        preview = "\n".join(f"- {name}" for name in over_limit[:5])
        extra = "" if len(over_limit) <= 5 else f"\n...and {len(over_limit) - 5} more."
        answer = QMessageBox.warning(
            w,
            "Batch includes long clips",
            (
                f"{len(over_limit)} pending clip{'s' if len(over_limit) != 1 else ''} exceed "
                f"the {w._preset.label} limit of {_fmt_duration(w._preset.max_duration)}:\n\n"
                f"{preview}{extra}\n\nExport the batch anyway?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _run_encode_job(self, info: VideoInfo, out_path: Path, entry: QueueEntry | None) -> None:
        w = self.win
        if self.detect_worker and self.detect_worker.isRunning():
            w._toast.show_toast("Wait for analysis to finish before exporting.", kind="warning")
            return
        try:
            plan = build_plan(
                info,
                w._preset,
                w._mode,
                manual_x=w._manual_x,
                track_points=self.track_points,
                scenes=self.scenes,
                adjustments=w._adjustments,
                overlays=w._overlays,
            )
        except Exception as e:
            w._toast.show_toast(f"Could not prepare export: {e}", kind="error")
            return

        trim_end = w._trim_high if w._trim_high and w._trim_high < info.duration else None
        trim_start = w._trim_low or 0.0
        if trim_end is None and trim_start <= 0.001:
            trim_start = 0.0

        out_choice = w._output_choice
        sub_choice = w._subtitle_choice
        # prefer the SRT stored per-clip if one exists
        srt_path = None
        burn = False
        if entry and entry.id in self.clip_subs:
            srt_path = self.clip_subs[entry.id]
            burn = bool(sub_choice and sub_choice.burn_in)
        elif sub_choice and sub_choice.srt_path and sub_choice.burn_in:
            srt_path = sub_choice.srt_path
            burn = True

        job = EncodeJob(
            info=info,
            preset=w._preset,
            plan=plan,
            out_path=out_path,
            trim_start=trim_start,
            trim_end=trim_end,
            encoder=out_choice.encoder if out_choice else None,
            quality=out_choice.quality if out_choice else 75,
            speed_preset=out_choice.speed_preset if out_choice else None,
            subtitles_path=srt_path,
            burn_subtitles=burn,
            caption_preset_id=(sub_choice.preset_id if sub_choice else None),
        )

        if entry:
            w._queue.update_status(entry.id, QueueStatus.ACTIVE, "encoding\u2026")

        w._log.clear()
        w._log.show()
        w._log.append(f"Mode: {w._mode.value}  \u00b7  {plan.notes}")
        w._export_progress.setValue(0)
        self.win._set_export_status("Encoding 0%", tone="accent")
        w._output_row.hide()
        w._export_btn.hide()
        w._cancel_btn.show()
        w._cancel_btn.setEnabled(True)
        w._export_all_btn.setEnabled(False)
        self._set_encode_busy(True)
        w._refresh_progress_hint()
        w._refresh_overview()

        self.encode_worker = EncodeWorker(job)
        self.encode_worker.progress.connect(self._on_export_progress)
        self.encode_worker.log.connect(self._append_log)
        self.encode_worker.finished_ok.connect(
            lambda out, eid=(entry.id if entry else None): self._on_export_done(out, eid)
        )
        self.encode_worker.failed.connect(
            lambda msg, eid=(entry.id if entry else None): self._on_export_fail(msg, eid)
        )
        self.encode_worker.start()

    def run_dry(self) -> None:
        w = self.win
        if not w._info:
            w._toast.show_toast("Load a clip first.", kind="warning")
            return
        from core.dryrun import build_report

        out_choice = w._output_choice
        try:
            report = build_report(
                info=w._info,
                preset=w._preset,
                mode=w._mode,
                track_points=self.track_points,
                scenes=self.scenes,
                adjustments=w._adjustments,
                encoder=out_choice.encoder if out_choice else None,
                quality=out_choice.quality if out_choice else 75,
                speed_preset=out_choice.speed_preset if out_choice else None,
                trim_start=w._trim_low or 0.0,
                trim_end=w._trim_high if w._trim_high and w._trim_high < w._info.duration else None,
                crop_width_frac=self._smart_track_crop_width_frac(),
            )
        except Exception as e:
            w._toast.show_toast(f"Dry-run failed: {e}", kind="error")
            return

        w._log.show()
        w._log.clear()
        w._log.append("Dry run \u2014 no files will be written")
        w._log.append("\u2500" * 58)
        for line in report.as_text().splitlines():
            w._log.append(line)
        self.win._set_export_status("Plan ready", tone="accent")
        w._refresh_progress_hint()
        w._toast.show_toast("Dry-run plan written to the export log.", kind="info")

    # --------------------------------------------------------------- scenes
    def kick_scene_detection(self, path: Path) -> None:
        """Fire-and-forget scene detection so the trim timeline can snap
        to real cuts. Cancels any in-flight scan from a previous clip."""
        if self.scene_worker and self.scene_worker.isRunning():
            self.scene_worker.cancel()

        worker = SceneWorker(path)
        worker.finished_ok.connect(self._on_scenes_ready)
        worker.failed.connect(lambda _msg: None)  # quiet failure — ticks are optional
        self.scene_worker = worker
        worker.start()

    def _on_scenes_ready(self, worker_path: str, scenes: list) -> None:
        w = self.win
        # Guard against stale results from a previous clip
        if not w._info:
            return
        current_path = Path(w._info.path)
        if Path(worker_path) != current_path:
            return
        self.scenes = scenes or []
        boundaries = [end for (_start, end) in self.scenes
                      if 0.0 < end < w._info.duration]
        w._player.set_shot_boundaries(boundaries)
        if hasattr(w, "_scene_label") and w._mode is ReframeMode.SMART_TRACK:
            if scenes:
                n = len(scenes)
                w._scene_label.setText(
                    f"{n} scene{'' if n == 1 else 's'} detected \u00b7 panning will respect cuts"
                )
            else:
                w._scene_label.setText("Continuous take \u2014 no hard cuts detected")
        w._refresh_overview()

    def _smart_track_crop_width_frac(self, *, info: VideoInfo | None = None) -> float | None:
        """Return the 9:16 viewport width as a fraction of source width,
        so the cameraman's safe-zone / big-jump thresholds scale
        correctly per clip. Returns None when geometry is unknown."""
        src = info or self.win._info
        if src is None or src.width <= 0 or src.height <= 0:
            return None
        target = self.win._preset.width / self.win._preset.height
        source = src.width / src.height
        if source >= target:
            crop_w = src.height * target
        else:
            crop_w = src.width
        return max(0.1, min(1.0, crop_w / src.width))

    def _default_output_path(self, info: VideoInfo) -> Path:
        stem = info.path.stem
        return info.path.with_name(f"{stem}_{self.win._preset.id}.mp4")

    # --------------------------------------------------------------- export UI
    def _append_log(self, line: str) -> None:
        log = self.win._log
        keep = line if len(line) <= 400 else line[:400] + "\u2026"
        log.append(keep)
        sb = log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _show_output_destination(self, path: Path) -> None:
        w = self.win
        w._output_label.setToolTip(str(path))
        label = f"Saved: {path.name}"
        width = max(180, w._output_label.width() or 280)
        w._output_label.setText(
            QFontMetrics(w._output_label.font()).elidedText(label, Qt.TextElideMode.ElideMiddle, width)
        )
        w._output_row.show()
        w._refresh_progress_hint()
        w._refresh_hero_header()

    def open_last_output_folder(self) -> None:
        if not self.last_output_path:
            return
        folder = (
            self.last_output_path
            if self.last_output_path.is_dir()
            else self.last_output_path.parent
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_export_progress(self, fraction: float) -> None:
        w = self.win
        pct = int(max(0.0, min(1.0, fraction)) * 100)
        w._export_progress.setValue(pct)
        self.win._set_export_status(f"Encoding {pct}%", tone="accent")
        w._refresh_overview()

    def _on_export_done(self, out: str, entry_id: int | None) -> None:
        w = self.win
        self.last_output_path = Path(out)
        w._export_progress.setValue(100)
        self.win._set_export_status("Complete", tone="success")
        self._append_log(f"[done] Exported {Path(out).name}")
        self._show_output_destination(Path(out))
        w._toast.show_toast(f"Exported {Path(out).name}", kind="success")
        if entry_id is not None:
            w._queue.update_status(entry_id, QueueStatus.DONE, "exported")
        w._refresh_queue_count()
        w._refresh_overview()
        if self.batch_running:
            self._advance_batch()
        else:
            self._reset_export_ui()

    def _on_export_fail(self, msg: str, entry_id: int | None) -> None:
        w = self.win
        self._append_log(f"[error] {msg}")
        cancelled = "cancel" in msg.lower()
        self.win._set_export_status("Cancelled" if cancelled else "Export failed", tone="warning")
        w._toast.show_toast(msg, kind="warning" if cancelled else "error")
        if entry_id is not None:
            w._queue.update_status(entry_id, QueueStatus.FAILED, msg)
        w._refresh_queue_count()
        w._refresh_overview()
        if self.batch_running:
            self._advance_batch()
        else:
            self._reset_export_ui()

    def cancel_active(self) -> None:
        w = self.win
        has_encode = bool(self.encode_worker and self.encode_worker.isRunning())
        has_detect = bool(self.detect_worker and self.detect_worker.isRunning())
        has_subs = bool(self.subtitle_worker and self.subtitle_worker.isRunning())
        has_vad = bool(self.vad_worker and self.vad_worker.isRunning())
        has_hl = bool(self.highlights_worker and self.highlights_worker.isRunning())
        has_ae = bool(self.auto_edit_worker and self.auto_edit_worker.isRunning())
        if not (has_encode or has_detect or has_subs or has_vad or has_hl or has_ae):
            return
        self.batch_running = False
        w._cancel_btn.setEnabled(False)
        self.win._set_export_status("Cancelling\u2026", tone="warning")
        if has_encode and self.encode_worker:
            self.encode_worker.cancel()
        if has_detect and self.detect_worker:
            self.detect_worker.cancel()
        if has_subs and self.subtitle_worker:
            self.subtitle_worker.cancel()
        if has_vad and self.vad_worker:
            self.vad_worker.cancel()
        if has_hl and self.highlights_worker:
            self.highlights_worker.cancel()
        if has_ae and self.auto_edit_worker:
            self.auto_edit_worker.cancel()
        w._refresh_overview()

    def _reset_export_ui(self) -> None:
        w = self.win
        w._export_btn.show()
        w._cancel_btn.hide()
        w._cancel_btn.setEnabled(True)
        self._set_encode_busy(False)
        w._refresh_queue_count()
        w._refresh_progress_hint()
        w._refresh_overview()

    def _set_encode_busy(self, busy: bool) -> None:
        w = self.win
        for btn in w._preset_buttons.values():
            btn.setEnabled(not busy)
        for card in w._mode_cards.values():
            card.setEnabled(not busy)
        w._drop.setEnabled(not busy)
        w._export_btn.setEnabled(not busy and w._info is not None)

    # --------------------------------------------------------------- batch
    def start_batch_export(self) -> None:
        from .file_dialogs import get_existing_directory
        w = self.win
        pending = w._queue.pending_entries()
        if not pending:
            return
        if not self._confirm_batch_platform_durations(pending):
            return
        out_dir = get_existing_directory(w, "Output folder for batch")
        if not out_dir:
            return
        self.batch_out_dir = Path(out_dir)
        self.batch_running = True
        w._toast.show_toast(f"Batch export started: {len(pending)} clips", kind="info")
        w._refresh_progress_hint()
        w._refresh_overview()
        self._advance_batch()

    def _advance_batch(self) -> None:
        w = self.win
        if not self.batch_running:
            self._reset_export_ui()
            return
        pending = w._queue.pending_entries()
        if not pending:
            self.batch_running = False
            self.win._set_export_status("Batch complete", tone="success")
            if self.batch_out_dir is not None:
                self.last_output_path = self.batch_out_dir
                self._show_output_destination(self.batch_out_dir)
            w._toast.show_toast("Batch export complete", kind="success")
            self._reset_export_ui()
            return
        entry = pending[0]
        self.suppress_auto_detect = True
        try:
            w._queue.select(entry.id)
        finally:
            self.suppress_auto_detect = False
        try:
            info = probe(entry.path)
        except Exception as e:
            w._queue.update_status(entry.id, QueueStatus.FAILED, f"probe: {e}")
            self._advance_batch()
            return
        w._info = info
        w._current_entry = entry
        w._trim_low = 0.0
        w._trim_high = info.duration
        w._refresh_platform_notice()
        w._refresh_overview()
        if w._mode is ReframeMode.SMART_TRACK:
            # For batch we re-detect per clip. Kick detect then encode when done.
            self.scenes = []
            self.track_points = []
            self._run_detect_then_encode(info, entry)
        else:
            assert self.batch_out_dir is not None  # set in start_batch_export
            out = self.batch_out_dir / f"{info.path.stem}_{w._preset.id}.mp4"
            self._run_encode_job(info, out, entry)

    def _run_detect_then_encode(self, info: VideoInfo, entry: QueueEntry) -> None:
        w = self.win
        w._set_detect_status(f"Batch analysis: {entry.path.name}", tone="accent")
        w._detect_progress.setValue(0)
        w._detect_progress.setFormat("Analysis %p%")
        w._detect_progress.show()
        w._refresh_detection_actions()
        w._refresh_overview()
        self.scenes = []
        self.kick_scene_detection(info.path)

        worker = DetectWorker(
            info.path,
            sample_fps=2.0,
            smoothing=0.65,
            crop_width_frac=self._smart_track_crop_width_frac(info=info),
        )
        worker.progress.connect(lambda v: w._detect_progress.setValue(int(v * 100)))

        def _done(points):
            self.track_points = points
            w._detect_progress.hide()
            w._refresh_detection_actions()
            w._refresh_overview()
            assert self.batch_out_dir is not None
            out = self.batch_out_dir / f"{info.path.stem}_{w._preset.id}.mp4"
            self._run_encode_job(info, out, entry)

        def _fail(msg):
            w._detect_progress.hide()
            w._queue.update_status(entry.id, QueueStatus.FAILED, f"detect: {msg}")
            w._refresh_detection_actions()
            w._refresh_overview()
            self._advance_batch()

        worker.finished_ok.connect(_done)
        worker.failed.connect(_fail)
        self.detect_worker = worker
        worker.start()
        w._refresh_detection_actions()
