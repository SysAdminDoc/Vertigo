"""Vertigo main window — premium composition, batch queue driver."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QCloseEvent, QDesktopServices, QFontMetrics
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QApplication,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.encode import EncodeJob
from core.overlays import TextOverlay
from core.presets import PRESETS, Preset, default_preset
from core.probe import VideoInfo, probe
from core.reframe import Adjustments, ReframeMode, build_plan
from core.scenes import detect_scenes
from core.subtitles import is_installed as subtitles_installed
from workers.detect_worker import DetectWorker
from workers.encode_worker import EncodeWorker
from workers.scene_worker import SceneWorker
from workers.subtitle_worker import SubtitleWorker

from .adjustments_panel import AdjustmentsPanel
from .batch_queue import BatchQueue, QueueEntry, QueueStatus
from .file_drop import FileDropZone
from .output_panel import OutputChoice, OutputPanel
from .overlays_panel import OverlaysPanel
from .subtitles_panel import SubtitleChoice, SubtitlesPanel
from .theme import apply_app_theme, sanitize_theme_preference, theme_choices
from .titlebar import TitleBar
from .video_player import VideoPlayer
from .widgets import GlassPanel, ModeCard, Toast


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Vertigo")
        self.setMinimumSize(1120, 720)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        # state -------------------------------------------------------
        self._settings = QSettings("Vertigo", "Vertigo")
        self._theme_preference = sanitize_theme_preference(
            self._settings.value("theme", "system", type=str)
        )
        self._info: VideoInfo | None = None
        self._current_entry: QueueEntry | None = None
        self._mode: ReframeMode = ReframeMode.CENTER
        self._preset: Preset = default_preset()
        self._manual_x: float = 0.5
        self._adjustments: Adjustments = Adjustments()
        self._track_points: list = []
        self._scenes: list[tuple[float, float]] = []
        self._trim_low: float = 0.0
        self._trim_high: float = 0.0

        self._detect_worker: DetectWorker | None = None
        self._encode_worker: EncodeWorker | None = None
        self._subtitle_worker: SubtitleWorker | None = None
        self._scene_worker: SceneWorker | None = None
        self._batch_running: bool = False
        self._suppress_auto_detect: bool = False
        self._last_output_path: Path | None = None

        # per-clip subtitle state keyed by queue entry id
        self._clip_subs: dict[int, Path] = {}
        self._output_choice: OutputChoice | None = None
        self._subtitle_choice: SubtitleChoice | None = None
        self._overlays: list[TextOverlay] = []

        self._build_chrome()
        self._build_body()
        self._wire()
        self._wire_system_theme()
        self._apply_theme(self._theme_preference, persist=False)
        self._on_mode_changed(ReframeMode.CENTER)
        self._update_preset_ui()

    # --------------------------------------------- chrome
    def _build_chrome(self) -> None:
        self._root = QWidget(self)
        self._root.setObjectName("rootWidget")
        root_lay = QVBoxLayout(self._root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        self._titlebar = TitleBar(self._root)
        self._titlebar.set_theme_choices(theme_choices(), self._theme_preference)
        self._titlebar.theme_changed.connect(self._on_theme_changed)
        self._titlebar.minimize_requested.connect(self.showMinimized)
        self._titlebar.toggle_max_requested.connect(self._toggle_max)
        self._titlebar.close_requested.connect(self.close)
        root_lay.addWidget(self._titlebar)

        self._body_host = QWidget()
        root_lay.addWidget(self._body_host, 1)

        self.setCentralWidget(self._root)
        self._toast = Toast(self._root)

    def _toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_theme_changed(self, preference: str) -> None:
        self._apply_theme(preference, persist=True)

    def _apply_theme(self, preference: str, *, persist: bool) -> None:
        self._theme_preference = sanitize_theme_preference(preference)
        app = QApplication.instance()
        if app is not None:
            apply_app_theme(app, self._theme_preference)
        self._titlebar.set_theme(self._theme_preference)
        if persist:
            self._settings.setValue("theme", self._theme_preference)
        self._refresh_themed_widgets()

    def _refresh_themed_widgets(self) -> None:
        if hasattr(self, "_mode_cards"):
            for card in self._mode_cards.values():
                card.refresh_theme()
        if hasattr(self, "_queue"):
            self._queue.refresh_theme()
        if hasattr(self, "_player"):
            self._player.refresh_theme()
        if hasattr(self, "_toast"):
            self._toast.refresh_theme()
        if hasattr(self, "_platform_notice"):
            self._refresh_platform_notice()

    def _wire_system_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        signal = getattr(app.styleHints(), "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(self._on_system_color_scheme_changed)

    def _on_system_color_scheme_changed(self, *args) -> None:
        if self._theme_preference == "system":
            self._apply_theme("system", persist=False)

    # --------------------------------------------- body
    def _build_body(self) -> None:
        body = QHBoxLayout(self._body_host)
        body.setContentsMargins(20, 20, 20, 20)
        body.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(10)
        self._splitter.addWidget(self._build_hero())
        self._splitter.addWidget(self._build_sidebar())
        self._splitter.setStretchFactor(0, 7)
        self._splitter.setStretchFactor(1, 4)
        self._splitter.setSizes([780, 420])
        body.addWidget(self._splitter)

    def _build_hero(self) -> QWidget:
        hero = GlassPanel()
        hero.setObjectName("heroPanel")
        lay = hero.layout()
        lay.setContentsMargins(22, 20, 22, 22)
        lay.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel("Preview")
        title.setObjectName("bigTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._meta_label = QLabel("Waiting for a clip")
        self._meta_label.setObjectName("statusPill")
        self._meta_label.setMaximumWidth(560)
        header.addWidget(self._meta_label)
        lay.addLayout(header)

        self._drop = FileDropZone()
        self._player = VideoPlayer()

        self._preview_stack = QStackedLayout()
        preview_host = QWidget()
        preview_host.setLayout(self._preview_stack)
        self._preview_stack.addWidget(self._drop)
        self._preview_stack.addWidget(self._player)
        lay.addWidget(preview_host, 1)

        return hero

    def _build_sidebar(self) -> QWidget:
        col = QVBoxLayout()
        col.setSpacing(12)
        col.setContentsMargins(0, 0, 0, 0)

        col.addWidget(self._build_preset_panel())
        col.addWidget(self._build_mode_panel())

        self._tabs = QTabWidget()
        self._tabs.setObjectName("sideTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._tabs.addTab(self._build_queue_tab(), "Queue")
        self._tabs.addTab(self._build_adjust_tab(), "Adjust")
        self._tabs.addTab(self._build_track_tab(), "Track")
        self._tabs.addTab(self._build_output_tab(), "Output")
        self._tabs.addTab(self._build_subs_tab(), "Captions")
        self._tabs.addTab(self._build_overlays_tab(), "Text")
        col.addWidget(self._tabs, 1)

        col.addLayout(self._build_action_bar())
        col.addWidget(self._build_progress_panel())

        host = QWidget()
        host.setLayout(col)
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return host

    def _build_preset_panel(self) -> QWidget:
        panel = GlassPanel("PLATFORM PRESET")
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)
        chip_grid = QGridLayout()
        chip_grid.setHorizontalSpacing(8)
        chip_grid.setVerticalSpacing(8)
        self._preset_buttons: dict[str, QPushButton] = {}
        for index, (pid, p) in enumerate(PRESETS.items()):
            btn = QPushButton(p.label)
            btn.setObjectName("presetChip")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(p.tagline)
            btn.setMinimumHeight(36)
            btn.setAccessibleName(f"{p.label} preset")
            btn.setAccessibleDescription(p.tagline)
            self._preset_group.addButton(btn)
            self._preset_buttons[pid] = btn
            chip_grid.addWidget(btn, index // 2, index % 2)
            btn.clicked.connect(lambda _=False, key=pid: self._choose_preset(key))
        panel.layout().addLayout(chip_grid)

        self._preset_detail = QLabel("")
        self._preset_detail.setObjectName("subtitle")
        self._preset_detail.setWordWrap(True)
        panel.layout().addWidget(self._preset_detail)

        self._platform_notice = QLabel("")
        self._platform_notice.setObjectName("inlineNotice")
        self._platform_notice.setWordWrap(True)
        self._platform_notice.hide()
        panel.layout().addWidget(self._platform_notice)
        self._preset_buttons["shorts"].setChecked(True)
        return panel

    def _build_mode_panel(self) -> QWidget:
        panel = GlassPanel("REFRAME MODE")
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)

        self._mode_cards = {
            ReframeMode.CENTER: ModeCard(
                "center", "Center crop",
                "Static crop for footage that is already centered."
            ),
            ReframeMode.SMART_TRACK: ModeCard(
                "smart_track", "Smart track",
                "Follows faces, never pans across a scene cut."
            ),
            ReframeMode.BLUR_LETTERBOX: ModeCard(
                "blur_letterbox", "Blur letterbox",
                "Keeps the full frame on a soft blurred backdrop."
            ),
            ReframeMode.MANUAL: ModeCard(
                "manual", "Manual crop",
                "Drag the viewport on the preview to lock a column."
            ),
        }
        for m, card in self._mode_cards.items():
            self._mode_group.addButton(card)
            panel.layout().addWidget(card)
            card.clicked.connect(lambda _=False, mode=m: self._on_mode_changed(mode))
        self._mode_cards[ReframeMode.CENTER].setChecked(True)
        return panel

    def _build_queue_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        hdr = QHBoxLayout()
        self._queue_count = QLabel("0 clips")
        self._queue_count.setObjectName("valueMuted")
        hdr.addWidget(self._queue_count)
        hdr.addStretch(1)
        clear = QPushButton("Clear queue")
        clear.setObjectName("ghostBtn")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._clear_queue)
        hdr.addWidget(clear)
        lay.addLayout(hdr)

        self._queue = BatchQueue()
        self._queue.entry_selected.connect(self._on_queue_select)
        self._queue.entry_removed.connect(self._on_queue_removed)
        lay.addWidget(self._queue, 1)
        return host

    def _build_adjust_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)

        self._adjust_panel = AdjustmentsPanel()
        self._adjust_panel.changed.connect(self._on_adjust_changed)
        lay.addWidget(self._adjust_panel)
        lay.addStretch(1)
        return host

    def _build_track_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(12)

        self._detect_status = QLabel("Load a clip to find faces and scene cuts.")
        self._detect_status.setObjectName("subtitle")
        self._detect_status.setWordWrap(True)
        lay.addWidget(self._detect_status)

        self._detect_progress = QProgressBar()
        self._detect_progress.setRange(0, 100)
        self._detect_progress.setValue(0)
        self._detect_progress.setTextVisible(False)
        self._detect_progress.hide()
        lay.addWidget(self._detect_progress)

        self._scene_label = QLabel("")
        self._scene_label.setObjectName("valueMuted")
        lay.addWidget(self._scene_label)

        self._detect_btn = QPushButton("Find subjects")
        self._detect_btn.setObjectName("ghostBtn")
        self._detect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detect_btn.setToolTip("Run Smart Track analysis on the loaded clip")
        self._detect_btn.setEnabled(False)
        self._detect_btn.clicked.connect(self._run_detect)
        lay.addWidget(self._detect_btn)

        self._dryrun_btn = QPushButton("Show plan (dry run)")
        self._dryrun_btn.setObjectName("ghostBtn")
        self._dryrun_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dryrun_btn.setToolTip(
            "Print the per-scene reframe plan without encoding. No file is written."
        )
        self._dryrun_btn.setEnabled(False)
        self._dryrun_btn.clicked.connect(self._run_dry)
        lay.addWidget(self._dryrun_btn)
        lay.addStretch(1)
        return host

    def _build_output_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        self._output_panel = OutputPanel()
        self._output_panel.changed.connect(self._on_output_changed)
        self._output_choice = self._output_panel.current_selection()
        lay.addWidget(self._output_panel)
        lay.addStretch(1)
        return host

    def _build_overlays_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        self._overlays_panel = OverlaysPanel()
        self._overlays_panel.overlays_changed.connect(self._on_overlays_changed)
        lay.addWidget(self._overlays_panel, 1)
        return host

    def _build_subs_tab(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        self._subs_panel = SubtitlesPanel()
        self._subs_panel.changed.connect(self._on_subs_changed)
        self._subs_panel.transcribe_requested.connect(self._run_transcribe)
        self._subs_panel.clear_requested.connect(self._on_subs_cleared)
        self._subtitle_choice = self._subs_panel.choice()
        lay.addWidget(self._subs_panel)
        return host

    def _build_action_bar(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._export_btn = QPushButton("Export")
        self._export_btn.setObjectName("primaryBtn")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.setToolTip("Export the selected clip using the current preset and mode")
        self._export_btn.setMinimumHeight(42)

        self._export_all_btn = QPushButton("Export all")
        self._export_all_btn.setObjectName("ghostBtn")
        self._export_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_all_btn.setEnabled(False)
        self._export_all_btn.setToolTip("Export every pending clip in the queue")
        self._export_all_btn.setMinimumHeight(42)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("destructiveGhost")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setToolTip("Cancel the active analysis or export")
        self._cancel_btn.setMinimumHeight(42)
        self._cancel_btn.hide()

        actions.addWidget(self._export_btn, 2)
        actions.addWidget(self._export_all_btn, 1)
        actions.addWidget(self._cancel_btn, 1)
        return actions

    def _build_progress_panel(self) -> QWidget:
        panel = GlassPanel()

        # Header row: label + idle-state status pill (collapses log when not busy)
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        hdr_label = QLabel("Export")
        hdr_label.setObjectName("sectionTitle")
        hdr.addWidget(hdr_label)
        hdr.addStretch(1)
        self._export_status = QLabel("Ready")
        self._export_status.setObjectName("valueMuted")
        hdr.addWidget(self._export_status)
        panel.layout().addLayout(hdr)

        self._export_progress = QProgressBar()
        self._export_progress.setRange(0, 100)
        self._export_progress.setValue(0)
        self._export_progress.setTextVisible(False)
        self._export_progress.setAccessibleName("Export progress")
        panel.layout().addWidget(self._export_progress)

        self._log = QTextEdit()
        self._log.setObjectName("logPanel")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(96)
        self._log.setPlaceholderText("Encoder output streams here during an export.")
        self._log.setAccessibleName("Export log")
        self._log.hide()   # revealed only while an export is running
        panel.layout().addWidget(self._log)

        self._output_row = QWidget()
        output_lay = QHBoxLayout(self._output_row)
        output_lay.setContentsMargins(0, 0, 0, 0)
        output_lay.setSpacing(10)
        self._output_label = QLabel("")
        self._output_label.setObjectName("valueMuted")
        self._output_label.setWordWrap(False)
        output_lay.addWidget(self._output_label, 1)
        self._open_output_btn = QPushButton("Reveal in folder")
        self._open_output_btn.setObjectName("ghostBtn")
        self._open_output_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_output_btn.setToolTip("Open the folder containing the latest export")
        self._open_output_btn.clicked.connect(self._open_last_output_folder)
        output_lay.addWidget(self._open_output_btn)
        self._output_row.hide()
        panel.layout().addWidget(self._output_row)
        return panel

    # --------------------------------------------- wiring
    def _wire(self) -> None:
        self._drop.file_dropped.connect(self._import_one)
        self._drop.files_dropped.connect(self._import_many)
        self._export_btn.clicked.connect(self._start_export)
        self._export_all_btn.clicked.connect(self._start_batch_export)
        self._cancel_btn.clicked.connect(self._cancel_active)
        self._player.canvas.viewport_dragged.connect(self._on_manual_drag)
        self._player.position_changed.connect(self._sync_track_pos)
        self._player.trim_changed.connect(self._on_trim_changed)

    # --------------------------------------------- preset
    def _choose_preset(self, pid: str) -> None:
        self._preset = PRESETS[pid]
        self._update_preset_ui()
        self._player.set_aspect(self._preset.width, self._preset.height)
        self._refresh_platform_notice()

    def _update_preset_ui(self) -> None:
        p = self._preset
        duration = (
            f"Trims longer than {p.max_duration}s will need approval"
            if p.max_duration
            else "No platform duration limit"
        )
        self._preset_detail.setText(
            f"{p.resolution_label} \u00b7 {p.fps}\u202ffps \u00b7 {p.video_bitrate} video \u00b7 {p.audio_bitrate} audio\n"
            f"{duration}."
        )
        self._refresh_platform_notice()

    def _refresh_platform_notice(self) -> None:
        if not hasattr(self, "_platform_notice"):
            return
        if not self._info:
            self._platform_notice.hide()
            return

        duration = max(0.0, (self._trim_high or self._info.duration) - (self._trim_low or 0.0))
        limit = self._preset.max_duration
        if limit and duration > limit:
            self._platform_notice.setProperty("tone", "warning")
            self._platform_notice.setText(
                f"Trim is {_fmt_duration(duration)}, above the {self._preset.label} limit of {_fmt_duration(limit)}."
            )
            self._platform_notice.show()
            if hasattr(self, "_export_btn"):
                self._export_btn.setToolTip("This trim exceeds the selected platform limit. You can still export.")
        elif limit:
            remaining = max(0.0, limit - duration)
            self._platform_notice.setProperty("tone", "success")
            self._platform_notice.setText(
                f"Trim fits {self._preset.label}; {_fmt_duration(remaining)} of headroom remains."
            )
            self._platform_notice.show()
            if hasattr(self, "_export_btn"):
                self._export_btn.setToolTip("Export the selected clip using the current preset and mode")
        else:
            self._platform_notice.hide()
            if hasattr(self, "_export_btn"):
                self._export_btn.setToolTip("Export the selected clip using the current preset and mode")
        self._platform_notice.style().unpolish(self._platform_notice)
        self._platform_notice.style().polish(self._platform_notice)

    # --------------------------------------------- mode
    def _on_mode_changed(self, mode: ReframeMode) -> None:
        self._mode = mode
        self._mode_cards[mode].setChecked(True)
        self._player.set_mode(mode.value)

        if mode is ReframeMode.SMART_TRACK:
            self._tabs.setCurrentIndex(2)  # TRACK tab
            if self._info is None:
                self._detect_status.setText("Load a clip to find faces and scene cuts.")
                self._scene_label.setText("")
                self._refresh_detection_actions()
                return
            if not self._track_points:
                if self._suppress_auto_detect:
                    self._detect_status.setText("Smart Track will analyze this clip during batch export.")
                else:
                    self._run_detect()
            else:
                self._detect_status.setText(f"Subject tracking ready: {len(self._track_points)} keyframes.")
        else:
            self._detect_progress.hide()
            if mode is ReframeMode.MANUAL:
                self._detect_status.setText("Manual mode: drag the crop frame in the preview.")
            elif mode is ReframeMode.BLUR_LETTERBOX:
                self._detect_status.setText("Blur Letterbox keeps the full frame and fills the background.")
            else:
                self._detect_status.setText("Center Crop is static and does not need analysis.")
        self._refresh_detection_actions()

    def _refresh_detection_actions(self) -> None:
        if not hasattr(self, "_detect_btn"):
            return
        running = bool(self._detect_worker and self._detect_worker.isRunning())
        can_analyze = self._info is not None and not running
        self._detect_btn.setEnabled(can_analyze)
        self._detect_btn.setText(
            "Finding subjects\u2026" if running else
            ("Run again" if self._track_points else "Find subjects")
        )
        if hasattr(self, "_dryrun_btn"):
            self._dryrun_btn.setEnabled(self._info is not None and not running)

    # --------------------------------------------- import
    def _import_one(self, path: str) -> None:
        entry = self._queue.add(Path(path))
        self._refresh_queue_count()
        self._queue.select(entry.id)

    def _import_many(self, paths: list[str]) -> None:
        first_id = None
        for p in paths:
            entry = self._queue.add(Path(p))
            if first_id is None:
                first_id = entry.id
        self._refresh_queue_count()
        self._toast.show_toast(f"Queued {len(paths)} clips", kind="success")
        if first_id is not None:
            self._queue.select(first_id)

    def _on_queue_select(self, entry: QueueEntry) -> None:
        self._current_entry = entry
        original_status = entry.status
        if original_status is QueueStatus.PENDING:
            self._queue.update_status(entry.id, QueueStatus.PENDING, "checking clip...")
        try:
            info = probe(entry.path)
        except Exception as e:
            self._queue.update_status(entry.id, QueueStatus.FAILED, "could not read clip")
            self._toast.show_toast(f"Could not read that clip \u2014 {e}", kind="error")
            return
        self._info = info
        self._track_points = []
        self._scenes = []
        self._scene_label.setText("")
        if original_status is QueueStatus.PENDING:
            self._queue.update_status(
                entry.id,
                QueueStatus.PENDING,
                f"ready · {_fmt_duration(info.duration)} · {info.width}x{info.height}",
            )
        self._set_meta_text(
            f"{entry.path.name} · {info.width}x{info.height} · {_fmt_duration(info.duration)} · {info.codec}"
        )
        self._player.load(entry.path)
        self._preview_stack.setCurrentWidget(self._player)
        self._player.set_shot_boundaries([])  # clear stale ticks from prior clip
        self._export_btn.setEnabled(True)
        self._titlebar.set_subtitle(f"Ready - {entry.path.name}")
        self._player.set_aspect(self._preset.width, self._preset.height)
        self._trim_low = 0.0
        self._trim_high = info.duration
        self._refresh_platform_notice()
        self._on_mode_changed(self._mode)
        if hasattr(self, "_subs_panel"):
            self._subs_panel.set_clip_loaded(True)
            self._subs_panel.set_srt_path(self._clip_subs.get(entry.id))
        self._kick_scene_detection(info.path)
        if hasattr(self, "_overlays_panel"):
            self._overlays_panel.set_duration(info.duration)

    def _refresh_queue_count(self) -> None:
        n = self._queue.count()
        entries = self._queue.entries()
        pending = len([e for e in entries if e.status is QueueStatus.PENDING])
        done = len([e for e in entries if e.status is QueueStatus.DONE])
        failed = len([e for e in entries if e.status is QueueStatus.FAILED])
        parts = [f"{n} clip{'s' if n != 1 else ''}", f"{pending} pending"]
        if done:
            parts.append(f"{done} done")
        if failed:
            parts.append(f"{failed} failed")
        self._queue_count.setText("  \u00b7  ".join(parts))
        self._export_all_btn.setEnabled(pending > 0)

    def _set_meta_text(self, text: str) -> None:
        self._meta_label.setToolTip(text)
        width = max(260, self._meta_label.maximumWidth() - 18)
        elided = QFontMetrics(self._meta_label.font()).elidedText(text, Qt.TextElideMode.ElideMiddle, width)
        self._meta_label.setText(elided)

    def _on_queue_removed(self, entry_id: int) -> None:
        self._refresh_queue_count()
        if self._current_entry and self._current_entry.id == entry_id:
            entries = self._queue.entries()
            if entries:
                self._queue.select(entries[0].id)
            else:
                self._clear_active_clip()

    def _clear_queue(self) -> None:
        if self._queue.count():
            answer = QMessageBox.question(
                self,
                "Clear queue?",
                "Remove all clips from the queue? Exported files are not affected.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._queue.clear()
        self._clear_active_clip()
        self._refresh_queue_count()

    def _clear_active_clip(self) -> None:
        self._current_entry = None
        self._info = None
        self._track_points = []
        self._scenes = []
        self._scene_label.setText("")
        self._detect_status.setText("Load a clip to find faces and scene cuts.")
        if self._scene_worker and self._scene_worker.isRunning():
            self._scene_worker.cancel()
        self._player.set_shot_boundaries([])
        self._player.clear()
        self._preview_stack.setCurrentWidget(self._drop)
        self._set_meta_text("Waiting for a clip")
        self._export_btn.setEnabled(False)
        self._export_all_btn.setEnabled(False)
        self._titlebar.set_subtitle("Vertical video studio")
        self._export_progress.setValue(0)
        self._set_export_status("Ready")
        self._log.clear()
        self._log.hide()
        self._last_output_path = None
        self._output_row.hide()
        self._refresh_platform_notice()
        self._refresh_detection_actions()
        if hasattr(self, "_subs_panel"):
            self._subs_panel.set_clip_loaded(False)
            self._subs_panel.set_srt_path(None)

    # --------------------------------------------- interactions
    def _on_manual_drag(self, x: float) -> None:
        self._manual_x = x

    def _sync_track_pos(self, t: float) -> None:
        if self._mode is not ReframeMode.SMART_TRACK or not self._track_points:
            return
        nearest = min(self._track_points, key=lambda p: abs(p.t - t))
        self._player.set_track_x(nearest.x)

    def _on_trim_changed(self, low: float, high: float) -> None:
        self._trim_low = low
        self._trim_high = high
        self._refresh_platform_notice()

    def _on_adjust_changed(self, adj: Adjustments) -> None:
        self._adjustments = adj

    def _on_output_changed(self, choice: OutputChoice) -> None:
        self._output_choice = choice

    def _on_subs_changed(self, choice: SubtitleChoice) -> None:
        self._subtitle_choice = choice

    def _on_overlays_changed(self, overlays: list) -> None:
        self._overlays = overlays

    def _on_subs_cleared(self) -> None:
        if self._current_entry and self._current_entry.id in self._clip_subs:
            path = self._clip_subs.pop(self._current_entry.id)
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    # --------------------------------------------- transcription
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

    def _on_subs_fail(self, msg: str) -> None:
        self._subs_panel.set_running(False)
        self._subs_panel.set_status(f"Transcription failed: {msg}")
        self._toast.show_toast(msg, kind="error")

    # --------------------------------------------- detection
    def _run_detect(self) -> None:
        if not self._info:
            self._toast.show_toast("Load a clip before running Smart Track.", kind="warning")
            self._refresh_detection_actions()
            return
        if self._detect_worker and self._detect_worker.isRunning():
            return
        self._detect_status.setText("Scanning for faces\u2026")
        self._detect_progress.setValue(0)
        self._detect_progress.setFormat("Analysis %p%")
        self._detect_progress.show()
        self._refresh_detection_actions()

        # Scene detection is already kicked off on clip load and its
        # result is stored in `self._scenes`. If the background worker
        # hasn't finished yet, fall back to an inline pass so Smart
        # Track isn't blocked waiting on it.
        if not self._scenes:
            try:
                self._scenes = detect_scenes(self._info.path)
            except Exception:
                self._scenes = []
        if self._scenes:
            n = len(self._scenes)
            self._scene_label.setText(f"{n} scene{'' if n == 1 else 's'} detected \u00b7 panning will respect cuts")
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

    def _on_detect_done(self, points: list) -> None:
        self._track_points = points
        self._detect_progress.hide()
        if not points:
            self._detect_status.setText("No faces detected \u2014 Export will fall back to a stable center crop.")
        else:
            extra = f" across {len(self._scenes)} scenes" if self._scenes else ""
            self._detect_status.setText(
                f"Tracking {len(points)} keyframes{extra}. Export will follow the subject."
            )
        if points:
            self._player.set_track_x(points[0].x)
        self._refresh_detection_actions()

    def _on_detect_fail(self, msg: str) -> None:
        self._detect_progress.hide()
        self._detect_status.setText(f"Detection failed: {msg}")
        self._toast.show_toast("Smart Track failed. Try Center Crop or Manual.", kind="error")
        self._refresh_detection_actions()

    # --------------------------------------------- export (single)
    def _start_export(self) -> None:
        if not self._info or not self._current_entry:
            return
        if not self._confirm_platform_duration():
            return
        suggested = self._default_output_path(self._info)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export vertical",
            str(suggested),
            "MP4 video (*.mp4)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
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
        self._set_export_status("Encoding 0%")
        self._encode_worker_percent = 0
        self._output_row.hide()
        self._export_btn.hide()
        self._cancel_btn.show()
        self._cancel_btn.setEnabled(True)
        self._export_all_btn.setEnabled(False)
        self._set_encode_busy(True)

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
        self._set_export_status("Plan ready")
        self._toast.show_toast("Dry-run plan written to the export log.", kind="info")

    def _kick_scene_detection(self, path: Path) -> None:
        """Fire-and-forget scene detection so the trim timeline can snap
        to real cuts. Cancels any in-flight scan from a previous clip."""
        if self._scene_worker and self._scene_worker.isRunning():
            self._scene_worker.cancel()
            self._scene_worker.wait(200)

        worker = SceneWorker(path)
        worker.finished_ok.connect(self._on_scenes_ready)
        worker.failed.connect(lambda _msg: None)  # quiet failure — ticks are optional
        self._scene_worker = worker
        worker.start()

    def _on_scenes_ready(self, scenes: list) -> None:
        # Guard against stale results from a previous clip
        if not self._info:
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

    def _open_last_output_folder(self) -> None:
        if not self._last_output_path:
            return
        folder = self._last_output_path if self._last_output_path.is_dir() else self._last_output_path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_export_progress(self, fraction: float) -> None:
        pct = int(max(0.0, min(1.0, fraction)) * 100)
        self._export_progress.setValue(pct)
        self._set_export_status(f"Encoding {pct}%")

    def _set_export_status(self, text: str) -> None:
        if hasattr(self, "_export_status"):
            self._export_status.setText(text)

    def _on_export_done(self, out: str, entry_id: int | None) -> None:
        self._last_output_path = Path(out)
        self._export_progress.setValue(100)
        self._set_export_status("Complete")
        self._append_log(f"[done] Exported {Path(out).name}")
        self._show_output_destination(Path(out))
        self._toast.show_toast(f"Exported {Path(out).name}", kind="success")
        if entry_id is not None:
            self._queue.update_status(entry_id, QueueStatus.DONE, "exported")
        self._refresh_queue_count()
        if self._batch_running:
            self._advance_batch()
        else:
            self._reset_export_ui()

    def _on_export_fail(self, msg: str, entry_id: int | None) -> None:
        self._append_log(f"[error] {msg}")
        cancelled = "cancel" in msg.lower()
        self._set_export_status("Cancelled" if cancelled else "Export failed")
        self._toast.show_toast(msg, kind="warning" if cancelled else "error")
        if entry_id is not None:
            self._queue.update_status(entry_id, QueueStatus.FAILED, msg)
        self._refresh_queue_count()
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
        self._set_export_status("Cancelling\u2026")
        if has_encode and self._encode_worker:
            self._encode_worker.cancel()
        if has_detect and self._detect_worker:
            self._detect_worker.cancel()
        if has_subs and self._subtitle_worker:
            self._subtitle_worker.cancel()

    def _reset_export_ui(self) -> None:
        self._export_btn.show()
        self._cancel_btn.hide()
        self._cancel_btn.setEnabled(True)
        self._set_encode_busy(False)
        self._refresh_queue_count()

    def _set_encode_busy(self, busy: bool) -> None:
        for btn in self._preset_buttons.values():
            btn.setEnabled(not busy)
        for card in self._mode_cards.values():
            card.setEnabled(not busy)
        self._drop.setEnabled(not busy)
        self._export_btn.setEnabled(not busy and self._info is not None)

    # --------------------------------------------- batch
    def _start_batch_export(self) -> None:
        pending = self._queue.pending_entries()
        if not pending:
            return
        if not self._confirm_batch_platform_durations(pending):
            return
        out_dir = QFileDialog.getExistingDirectory(
            self,
            "Output folder for batch",
            "",
            QFileDialog.Option.DontUseNativeDialog,
        )
        if not out_dir:
            return
        self._batch_out_dir = Path(out_dir)
        self._batch_running = True
        self._toast.show_toast(f"Batch export started: {len(pending)} clips", kind="info")
        self._advance_batch()

    def _advance_batch(self) -> None:
        if not self._batch_running:
            self._reset_export_ui()
            return
        pending = self._queue.pending_entries()
        if not pending:
            self._batch_running = False
            self._set_export_status("Batch complete")
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
        if self._mode is ReframeMode.SMART_TRACK:
            # For batch we re-detect per clip. Kick detect then encode when done.
            self._scenes = []
            self._track_points = []
            self._run_detect_then_encode(info, entry)
        else:
            out = self._batch_out_dir / f"{info.path.stem}_{self._preset.id}.mp4"
            self._run_encode_job(info, out, entry)

    def _run_detect_then_encode(self, info: VideoInfo, entry: QueueEntry) -> None:
        self._detect_status.setText(f"Batch analysis: {entry.path.name}")
        self._detect_progress.setValue(0)
        self._detect_progress.setFormat("Analysis %p%")
        self._detect_progress.show()
        self._refresh_detection_actions()
        try:
            self._scenes = detect_scenes(info.path)
        except Exception:
            self._scenes = []

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
            out = self._batch_out_dir / f"{info.path.stem}_{self._preset.id}.mp4"
            self._run_encode_job(info, out, entry)
        def _fail(msg):
            self._detect_progress.hide()
            self._queue.update_status(entry.id, QueueStatus.FAILED, f"detect: {msg}")
            self._refresh_detection_actions()
            self._advance_batch()
        worker.finished_ok.connect(_done)
        worker.failed.connect(_fail)
        self._detect_worker = worker
        worker.start()
        self._refresh_detection_actions()

    # --------------------------------------------- lifecycle
    def closeEvent(self, event: QCloseEvent) -> None:
        self._cancel_active()
        if self._encode_worker:
            self._encode_worker.wait(1500)
        if self._detect_worker:
            self._detect_worker.wait(1500)
        if self._subtitle_worker:
            self._subtitle_worker.wait(1500)
        super().closeEvent(event)


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
