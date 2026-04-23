"""Vertigo main-window controller — worker lifecycle and batch driver.

Extracted from ``ui/main_window.py`` so the window module can stay focused
on composition + layout + UI-state helpers. This mixin owns the methods
that kick off and observe the long-running jobs:

  * caption transcription  (SubtitleWorker)
  * face detection         (DetectWorker)
  * scene detection        (SceneWorker)
  * video encoding         (EncodeWorker)
  * batch export driver    (_start_batch_export / _advance_batch /
                            _run_detect_then_encode)

Design notes:

  - All state stays on ``MainWindow`` — this is a pure behaviour mixin
    that inherits nothing and accesses ``self._foo`` the same way the
    original inline methods did. Nothing changes semantically; the only
    difference is the file location of the method definitions.
  - No public method names change. Every ``_foo`` here used to live on
    ``MainWindow`` under the exact same name, so existing callers (UI
    wiring in main_window._wire(), panels/* signal emitters, worker
    signal connects) continue to resolve via normal Python MRO.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontMetrics
from PyQt6.QtWidgets import QMessageBox

from core.encode import EncodeJob
from core.probe import VideoInfo, probe
from core.reframe import ReframeMode, build_plan
from core.subtitles import is_installed as subtitles_installed
from workers.detect_worker import DetectWorker
from workers.encode_worker import EncodeWorker
from workers.scene_worker import SceneWorker
from workers.subtitle_worker import SubtitleWorker

from .batch_queue import QueueEntry, QueueStatus


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class MainControllerMixin:
    """Behaviour mixin for MainWindow — worker kickoffs, batch, signal handlers.

    Designed to be mixed into ``MainWindow`` *before* ``QMainWindow`` in the
    class declaration so normal Qt base-class behaviour is preserved.
    """

    # --------------------------------------------- captions
    def _on_subs_cleared(self) -> None:
        if self._current_entry and self._current_entry.id in self._clip_subs:
            path = self._clip_subs.pop(self._current_entry.id)
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        self._refresh_overview()

    def _run_transcribe(
        self,
        model: str,
        language: str | None,
        preset_id: str = "pop",
        face_aware: bool = False,
    ) -> None:
        if not self._info or not self._current_entry:
            self._toast.show_toast("Load a clip first.", kind="warning")
            return
        if self._subtitle_worker and self._subtitle_worker.isRunning():
            return

        from core.caption_styles import resolve as resolve_caption_preset
        preset = resolve_caption_preset(preset_id)

        is_letterbox = self._mode is ReframeMode.BLUR_LETTERBOX

        out_dir = self._info.path.parent
        self._subs_panel.set_running(True)
        face_note = "  \u00b7  face-aware" if face_aware and not is_letterbox else ""
        self._subs_panel.set_status(
            f"Transcribing {self._info.path.name} with whisper-{model} \u2014 {preset.label} style{face_note}"
        )
        if not subtitles_installed():
            self._subs_panel.set_status("Installing faster-whisper (one-time, ~200 MB)\u2026")
        self._refresh_overview()

        entry_id = self._current_entry.id
        self._subtitle_worker = SubtitleWorker(
            self._info.path,
            out_dir,
            preset=preset,
            height_px=self._preset.height,
            model_name=model,
            language=language,
            face_aware=face_aware,
            letterbox=is_letterbox,
        )
        self._subtitle_worker.progress.connect(self._subs_panel.set_progress)
        self._subtitle_worker.status.connect(self._subs_panel.set_status)
        self._subtitle_worker.finished_ok.connect(
            lambda srt, eid=entry_id: self._on_subs_done(srt, eid)
        )
        self._subtitle_worker.failed.connect(self._on_subs_fail)
        self._subtitle_worker.start()

    def _on_subs_done(self, srt_str: str, entry_id: int) -> None:
        srt = Path(srt_str)
        self._clip_subs[entry_id] = srt
        self._subs_panel.set_running(False)
        if self._current_entry and self._current_entry.id == entry_id:
            self._subs_panel.set_srt_path(srt)
        self._toast.show_toast(f"Captions ready: {srt.name}", kind="success")
        self._refresh_overview()

    def _on_subs_fail(self, msg: str) -> None:
        self._subs_panel.set_running(False)
        self._subs_panel.set_status(f"Transcription failed: {msg}", tone="warning")
        self._toast.show_toast(msg, kind="error")
        self._refresh_overview()

    # --------------------------------------------- detection
    def _run_detect(self) -> None:
        if not self._info:
            self._toast.show_toast("Load a clip before running Smart Track.", kind="warning")
            self._refresh_detection_actions()
            return
        if self._detect_worker and self._detect_worker.isRunning():
            return
        self._set_detect_status("Scanning for faces\u2026", tone="accent")
        self._detect_progress.setValue(0)
        self._detect_progress.setFormat("Analysis %p%")
        self._detect_progress.show()
        self._refresh_detection_actions()

        if self._scenes:
            n = len(self._scenes)
            self._scene_label.setText(f"{n} scene{'' if n == 1 else 's'} detected \u00b7 panning will respect cuts")
        elif self._scene_worker and self._scene_worker.isRunning():
            self._scene_label.setText("Scene cuts are still loading in the background.")
        else:
            self._scene_label.setText("Continuous take \u2014 no hard cuts detected")

        self._detect_worker = DetectWorker(
            self._info.path,
            sample_fps=2.0,
            smoothing=0.65,
            crop_width_frac=self._smart_track_crop_width_frac(),
        )
        self._detect_worker.progress.connect(
            lambda v: self._detect_progress.setValue(int(v * 100))
        )
        self._detect_worker.finished_ok.connect(self._on_detect_done)
        self._detect_worker.failed.connect(self._on_detect_fail)
        self._detect_worker.start()
        self._refresh_detection_actions()
        self._refresh_overview()

    def _on_detect_done(self, points: list) -> None:
        self._track_points = points
        self._detect_progress.hide()
        if not points:
            self._set_detect_status(
                "No faces detected \u2014 export will fall back to a stable center crop.",
                tone="warning",
            )
        else:
            extra = f" across {len(self._scenes)} scenes" if self._scenes else ""
            self._set_detect_status(
                f"Tracking {len(points)} keyframes{extra}. Export will follow the subject.",
                tone="success",
            )
        if points:
            self._player.set_track_x(points[0].x)
        self._refresh_detection_actions()
        self._refresh_overview()

    def _on_detect_fail(self, msg: str) -> None:
        self._detect_progress.hide()
        self._set_detect_status(f"Detection failed: {msg}", tone="warning")
        self._toast.show_toast("Smart Track failed. Try Center Crop or Manual.", kind="error")
        self._refresh_detection_actions()
        self._refresh_overview()

    # --------------------------------------------- export (single)
    def _start_export(self) -> None:
        if not self._info or not self._current_entry:
            return
        if not self._confirm_platform_duration():
            return
        from .file_dialogs import get_save_video_path
        suggested = self._default_output_path(self._info)
        path = get_save_video_path(self, suggested)
        if not path:
            return
        self._run_encode_job(self._info, Path(path), self._current_entry)

    def _confirm_platform_duration(self) -> bool:
        if not self._info or not self._preset.max_duration:
            return True
        duration = max(0.0, (self._trim_high or self._info.duration) - (self._trim_low or 0.0))
        if duration <= self._preset.max_duration:
            return True
        answer = QMessageBox.warning(
            self,
            "Export above platform limit?",
            (
                f"The current trim is {_fmt_duration(duration)}, which is longer than "
                f"the {self._preset.label} limit of {_fmt_duration(self._preset.max_duration)}.\n\n"
                "Export anyway?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_batch_platform_durations(self, entries: list[QueueEntry]) -> bool:
        if not self._preset.max_duration:
            return True

        over_limit: list[str] = []
        for entry in entries:
            try:
                info = probe(entry.path)
            except Exception:
                continue
            if info.duration > self._preset.max_duration:
                over_limit.append(f"{entry.path.name} ({_fmt_duration(info.duration)})")

        if not over_limit:
            return True

        preview = "\n".join(f"- {name}" for name in over_limit[:5])
        extra = "" if len(over_limit) <= 5 else f"\n...and {len(over_limit) - 5} more."
        answer = QMessageBox.warning(
            self,
            "Batch includes long clips",
            (
                f"{len(over_limit)} pending clip{'s' if len(over_limit) != 1 else ''} exceed "
                f"the {self._preset.label} limit of {_fmt_duration(self._preset.max_duration)}:\n\n"
                f"{preview}{extra}\n\nExport the batch anyway?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _run_encode_job(self, info: VideoInfo, out_path: Path, entry: QueueEntry | None) -> None:
        if self._detect_worker and self._detect_worker.isRunning():
            self._toast.show_toast("Wait for analysis to finish before exporting.", kind="warning")
            return
        try:
            plan = build_plan(
                info,
                self._preset,
                self._mode,
                manual_x=self._manual_x,
                track_points=self._track_points,
                scenes=self._scenes,
                adjustments=self._adjustments,
                overlays=self._overlays,
            )
        except Exception as e:
            self._toast.show_toast(f"Could not prepare export: {e}", kind="error")
            return

        trim_end = self._trim_high if self._trim_high and self._trim_high < info.duration else None
        trim_start = self._trim_low or 0.0
        if trim_end is None and trim_start <= 0.001:
            trim_start = 0.0

        out_choice = self._output_choice
        sub_choice = self._subtitle_choice
        # prefer the SRT stored per-clip if one exists
        srt_path = None
        burn = False
        if entry and entry.id in self._clip_subs:
            srt_path = self._clip_subs[entry.id]
            burn = bool(sub_choice and sub_choice.burn_in)
        elif sub_choice and sub_choice.srt_path and sub_choice.burn_in:
            srt_path = sub_choice.srt_path
            burn = True

        job = EncodeJob(
            info=info,
            preset=self._preset,
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
            self._queue.update_status(entry.id, QueueStatus.ACTIVE, "encoding\u2026")

        self._log.clear()
        self._log.show()
        self._log.append(f"Mode: {self._mode.value}  \u00b7  {plan.notes}")
        self._export_progress.setValue(0)
        self._set_export_status("Encoding 0%", tone="accent")
        self._encode_worker_percent = 0
        self._output_row.hide()
        self._export_btn.hide()
        self._cancel_btn.show()
        self._cancel_btn.setEnabled(True)
        self._export_all_btn.setEnabled(False)
        self._set_encode_busy(True)
        self._refresh_progress_hint()
        self._refresh_overview()

        self._encode_worker = EncodeWorker(job)
        self._encode_worker.progress.connect(self._on_export_progress)
        self._encode_worker.log.connect(self._append_log)
        self._encode_worker.finished_ok.connect(
            lambda out, eid=(entry.id if entry else None): self._on_export_done(out, eid)
        )
        self._encode_worker.failed.connect(
            lambda msg, eid=(entry.id if entry else None): self._on_export_fail(msg, eid)
        )
        self._encode_worker.start()

    def _run_dry(self) -> None:
        if not self._info:
            self._toast.show_toast("Load a clip first.", kind="warning")
            return
        from core.dryrun import build_report

        out_choice = self._output_choice
        try:
            report = build_report(
                info=self._info,
                preset=self._preset,
                mode=self._mode,
                track_points=self._track_points,
                scenes=self._scenes,
                adjustments=self._adjustments,
                encoder=out_choice.encoder if out_choice else None,
                quality=out_choice.quality if out_choice else 75,
                speed_preset=out_choice.speed_preset if out_choice else None,
                trim_start=self._trim_low or 0.0,
                trim_end=self._trim_high if self._trim_high and self._trim_high < self._info.duration else None,
                crop_width_frac=self._smart_track_crop_width_frac(),
            )
        except Exception as e:
            self._toast.show_toast(f"Dry-run failed: {e}", kind="error")
            return

        self._log.show()
        self._log.clear()
        self._log.append("Dry run \u2014 no files will be written")
        self._log.append("\u2500" * 58)
        for line in report.as_text().splitlines():
            self._log.append(line)
        self._set_export_status("Plan ready", tone="accent")
        self._refresh_progress_hint()
        self._toast.show_toast("Dry-run plan written to the export log.", kind="info")

    def _kick_scene_detection(self, path: Path) -> None:
        """Fire-and-forget scene detection so the trim timeline can snap
        to real cuts. Cancels any in-flight scan from a previous clip."""
        if self._scene_worker and self._scene_worker.isRunning():
            self._scene_worker.cancel()

        worker = SceneWorker(path)
        worker.finished_ok.connect(self._on_scenes_ready)
        worker.failed.connect(lambda _msg: None)  # quiet failure — ticks are optional
        self._scene_worker = worker
        worker.start()

    def _on_scenes_ready(self, worker_path: str, scenes: list) -> None:
        # Guard against stale results from a previous clip
        if not self._info:
            return
        current_path = Path(self._info.path)
        if Path(worker_path) != current_path:
            return
        self._scenes = scenes or []
        boundaries = [end for (_start, end) in self._scenes
                      if 0.0 < end < self._info.duration]
        self._player.set_shot_boundaries(boundaries)
        if hasattr(self, "_scene_label") and self._mode is ReframeMode.SMART_TRACK:
            if scenes:
                n = len(scenes)
                self._scene_label.setText(
                    f"{n} scene{'' if n == 1 else 's'} detected \u00b7 panning will respect cuts"
                )
            else:
                self._scene_label.setText("Continuous take \u2014 no hard cuts detected")
        self._refresh_overview()

    def _smart_track_crop_width_frac(self, *, info: VideoInfo | None = None) -> float | None:
        """Return the 9:16 viewport width as a fraction of source width,
        so the cameraman's safe-zone / big-jump thresholds scale
        correctly per clip. Returns None when geometry is unknown."""
        src = info or self._info
        if src is None or src.width <= 0 or src.height <= 0:
            return None
        target = self._preset.width / self._preset.height
        source = src.width / src.height
        if source >= target:
            crop_w = src.height * target
        else:
            crop_w = src.width
        return max(0.1, min(1.0, crop_w / src.width))

    def _default_output_path(self, info: VideoInfo) -> Path:
        stem = info.path.stem
        return info.path.with_name(f"{stem}_{self._preset.id}.mp4")

    def _append_log(self, line: str) -> None:
        keep = line if len(line) <= 400 else line[:400] + "\u2026"
        self._log.append(keep)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _show_output_destination(self, path: Path) -> None:
        self._output_label.setToolTip(str(path))
        label = f"Saved: {path.name}"
        width = max(180, self._output_label.width() or 280)
        self._output_label.setText(
            QFontMetrics(self._output_label.font()).elidedText(label, Qt.TextElideMode.ElideMiddle, width)
        )
        self._output_row.show()
        self._refresh_progress_hint()
        self._refresh_hero_header()

    def _open_last_output_folder(self) -> None:
        if not self._last_output_path:
            return
        folder = self._last_output_path if self._last_output_path.is_dir() else self._last_output_path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_export_progress(self, fraction: float) -> None:
        pct = int(max(0.0, min(1.0, fraction)) * 100)
        self._export_progress.setValue(pct)
        self._set_export_status(f"Encoding {pct}%", tone="accent")
        self._refresh_overview()

    def _set_export_status(self, text: str, tone: str | None = None) -> None:
        if hasattr(self, "_export_status"):
            self._export_status.setText(text)
            self._export_status.setProperty("tone", tone)
            self._export_status.style().unpolish(self._export_status)
            self._export_status.style().polish(self._export_status)

    def _on_export_done(self, out: str, entry_id: int | None) -> None:
        self._last_output_path = Path(out)
        self._export_progress.setValue(100)
        self._set_export_status("Complete", tone="success")
        self._append_log(f"[done] Exported {Path(out).name}")
        self._show_output_destination(Path(out))
        self._toast.show_toast(f"Exported {Path(out).name}", kind="success")
        if entry_id is not None:
            self._queue.update_status(entry_id, QueueStatus.DONE, "exported")
        self._refresh_queue_count()
        self._refresh_overview()
        if self._batch_running:
            self._advance_batch()
        else:
            self._reset_export_ui()

    def _on_export_fail(self, msg: str, entry_id: int | None) -> None:
        self._append_log(f"[error] {msg}")
        cancelled = "cancel" in msg.lower()
        self._set_export_status("Cancelled" if cancelled else "Export failed", tone="warning")
        self._toast.show_toast(msg, kind="warning" if cancelled else "error")
        if entry_id is not None:
            self._queue.update_status(entry_id, QueueStatus.FAILED, msg)
        self._refresh_queue_count()
        self._refresh_overview()
        if self._batch_running:
            self._advance_batch()
        else:
            self._reset_export_ui()

    def _cancel_active(self) -> None:
        has_encode = bool(self._encode_worker and self._encode_worker.isRunning())
        has_detect = bool(self._detect_worker and self._detect_worker.isRunning())
        has_subs = bool(self._subtitle_worker and self._subtitle_worker.isRunning())
        if not has_encode and not has_detect and not has_subs:
            return
        self._batch_running = False
        self._cancel_btn.setEnabled(False)
        self._set_export_status("Cancelling\u2026", tone="warning")
        if has_encode and self._encode_worker:
            self._encode_worker.cancel()
        if has_detect and self._detect_worker:
            self._detect_worker.cancel()
        if has_subs and self._subtitle_worker:
            self._subtitle_worker.cancel()
        self._refresh_overview()

    def _reset_export_ui(self) -> None:
        self._export_btn.show()
        self._cancel_btn.hide()
        self._cancel_btn.setEnabled(True)
        self._set_encode_busy(False)
        self._refresh_queue_count()
        self._refresh_progress_hint()
        self._refresh_overview()

    def _set_encode_busy(self, busy: bool) -> None:
        for btn in self._preset_buttons.values():
            btn.setEnabled(not busy)
        for card in self._mode_cards.values():
            card.setEnabled(not busy)
        self._drop.setEnabled(not busy)
        self._export_btn.setEnabled(not busy and self._info is not None)

    # --------------------------------------------- batch
    def _start_batch_export(self) -> None:
        from .file_dialogs import get_existing_directory
        pending = self._queue.pending_entries()
        if not pending:
            return
        if not self._confirm_batch_platform_durations(pending):
            return
        out_dir = get_existing_directory(self, "Output folder for batch")
        if not out_dir:
            return
        self._batch_out_dir = Path(out_dir)
        self._batch_running = True
        self._toast.show_toast(f"Batch export started: {len(pending)} clips", kind="info")
        self._refresh_progress_hint()
        self._refresh_overview()
        self._advance_batch()

    def _advance_batch(self) -> None:
        if not self._batch_running:
            self._reset_export_ui()
            return
        pending = self._queue.pending_entries()
        if not pending:
            self._batch_running = False
            self._set_export_status("Batch complete", tone="success")
            if hasattr(self, "_batch_out_dir"):
                self._last_output_path = self._batch_out_dir
                self._show_output_destination(self._batch_out_dir)
            self._toast.show_toast("Batch export complete", kind="success")
            self._reset_export_ui()
            return
        entry = pending[0]
        self._suppress_auto_detect = True
        try:
            self._queue.select(entry.id)
        finally:
            self._suppress_auto_detect = False
        try:
            info = probe(entry.path)
        except Exception as e:
            self._queue.update_status(entry.id, QueueStatus.FAILED, f"probe: {e}")
            self._advance_batch()
            return
        self._info = info
        self._current_entry = entry
        self._trim_low = 0.0
        self._trim_high = info.duration
        self._refresh_platform_notice()
        self._refresh_overview()
        if self._mode is ReframeMode.SMART_TRACK:
            # For batch we re-detect per clip. Kick detect then encode when done.
            self._scenes = []
            self._track_points = []
            self._run_detect_then_encode(info, entry)
        else:
            out = self._batch_out_dir / f"{info.path.stem}_{self._preset.id}.mp4"
            self._run_encode_job(info, out, entry)

    def _run_detect_then_encode(self, info: VideoInfo, entry: QueueEntry) -> None:
        self._set_detect_status(f"Batch analysis: {entry.path.name}", tone="accent")
        self._detect_progress.setValue(0)
        self._detect_progress.setFormat("Analysis %p%")
        self._detect_progress.show()
        self._refresh_detection_actions()
        self._refresh_overview()
        self._scenes = []
        self._kick_scene_detection(info.path)

        worker = DetectWorker(
            info.path,
            sample_fps=2.0,
            smoothing=0.65,
            crop_width_frac=self._smart_track_crop_width_frac(info=info),
        )
        worker.progress.connect(lambda v: self._detect_progress.setValue(int(v * 100)))

        def _done(points):
            self._track_points = points
            self._detect_progress.hide()
            self._refresh_detection_actions()
            self._refresh_overview()
            out = self._batch_out_dir / f"{info.path.stem}_{self._preset.id}.mp4"
            self._run_encode_job(info, out, entry)

        def _fail(msg):
            self._detect_progress.hide()
            self._queue.update_status(entry.id, QueueStatus.FAILED, f"detect: {msg}")
            self._refresh_detection_actions()
            self._refresh_overview()
            self._advance_batch()

        worker.finished_ok.connect(_done)
        worker.failed.connect(_fail)
        self._detect_worker = worker
        worker.start()
        self._refresh_detection_actions()
