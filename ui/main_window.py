"""
main_window.py
Primary application window for Screen Trigger Macro.
Implements the sidebar navigation, all content pages, and the OCR/scanning
background thread. All cross-thread communication uses Qt signals.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from threading import Event, Thread
from typing import Any

import keyboard
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.action_executor import ActionExecutor
from core.config_manager import ConfigManager
from core.ocr_engine import (
    OcrEngine,
    OcrResult,
    TESS_CONFIG_BLOCK,
    TESS_CONFIG_LINE,
    TESS_CONFIG_SPARSE,
)
from core.screen_capture import (
    ScreenCapture,
    PREPROCESS_AUTO,
    PREPROCESS_GAME,
    PREPROCESS_LIGHT,
    get_dpi_scale,
)
from core.trigger_engine import TriggerEngine, TriggerMatch
from ui.region_selector import RegionSelector
from ui.styles import (
    ACCENT_DANGER,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    ACCENT_WARNING,
    BG_ELEVATED,
    BG_PANEL,
    BG_SURFACE,
    BORDER_DEFAULT,
    DISABLED_BADGE,
    ENABLED_BADGE,
    SIDEBAR_WIDTH,
    STYLESHEET,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from ui.trigger_dialog import TriggerDialog

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────── #
# Worker thread signals bridge                                                 #
# ──────────────────────────────────────────────────────────────────────────── #


class ScannerSignals(QWidget):
    """Thin QObject used exclusively to ferry signals from worker to UI thread."""

    ocr_result = Signal(str, float)          # text, avg_confidence
    trigger_matched = Signal(str, str, str)  # trigger_name, matched_text, action_str
    scan_stats = Signal(float, int)          # scans_per_second, total_matches
    error_occurred = Signal(str)


# ──────────────────────────────────────────────────────────────────────────── #
# Main Window                                                                  #
# ──────────────────────────────────────────────────────────────────────────── #


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Screen Trigger Macro")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 780)

        # Core subsystems
        self._config = ConfigManager()
        self._ocr = OcrEngine(
            # Lowered default from 60 → 30: FFXI bitmap font scores 35-65 per word;
            # threshold=60 silently drops most valid game text before matching.
            confidence_threshold=self._config.get("ocr_confidence_threshold", 30),
            tesseract_config=self._config.get("tesseract_config", "--psm 11 --oem 3"),
        )
        self._capture = ScreenCapture()
        # Apply saved preprocess mode (auto / light / game)
        self._capture.preprocess_mode = self._config.get("preprocess_mode", "auto")
        self._trigger_engine = TriggerEngine()
        self._executor = ActionExecutor()
        self._signals = ScannerSignals()

        # Runtime state
        self._scanning = False
        self._scan_thread: Thread | None = None
        self._stop_event = Event()
        self._total_matches = 0
        self._scan_count = 0
        self._scan_count_window = 0
        self._last_stats_time = time.monotonic()
        self._start_time: float | None = None

        # Load triggers
        self._trigger_engine.set_triggers(self._config.get_triggers())

        # Build UI
        self._build_ui()
        self._connect_signals()
        self._setup_tray()
        self._setup_global_hotkeys()
        self._executor.start()

        # Uptime ticker
        self._uptime_timer = QTimer(self)
        self._uptime_timer.timeout.connect(self._update_uptime)
        self._uptime_timer.start(1000)

        self.setStyleSheet(STYLESHEET)
        logger.info("MainWindow initialised")

    # ================================================================== #
    # UI Construction                                                      #
    # ================================================================== #

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        self._sidebar = self._build_sidebar()
        root_layout.addWidget(self._sidebar)

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentArea")
        root_layout.addWidget(self._stack, 1)

        # Pages
        self._page_dashboard = self._build_dashboard()
        self._page_triggers = self._build_triggers_page()
        self._page_logs = self._build_logs_page()
        self._page_settings = self._build_settings_page()

        self._stack.addWidget(self._page_dashboard)
        self._stack.addWidget(self._page_triggers)
        self._stack.addWidget(self._page_logs)
        self._stack.addWidget(self._page_settings)

        self._nav_buttons: list[QPushButton] = []
        self._active_nav_index = 0
        self._nav_to(0)

    # ── Sidebar ──────────────────────────────────────────────────────── #

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(4)

        # Logo / title
        logo_label = QLabel("⬡  STM")
        logo_label.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {ACCENT_PRIMARY}; letter-spacing: -0.5px; padding: 4px 8px 16px 8px;"
        )
        layout.addWidget(logo_label)

        nav_items = [
            ("dashboard", "  Dashboard"),
            ("triggers", "  Triggers"),
            ("logs", "  Logs"),
            ("settings", "  Settings"),
        ]

        self._nav_buttons = []
        for i, (_, label) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(False)
            btn.setProperty("active", "false")
            btn.clicked.connect(lambda checked, idx=i: self._nav_to(idx))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()

        # Status indicator
        status_row = QHBoxLayout()
        self._status_dot = QLabel()
        self._status_dot.setObjectName("StatusDot")
        self._status_dot.setProperty("status", "stopped")
        self._status_dot.setFixedSize(10, 10)
        self._status_label = QLabel("Stopped")
        self._status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        status_row.addWidget(self._status_dot)
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        return sidebar

    # ── Dashboard ────────────────────────────────────────────────────── #

    def _build_dashboard(self) -> QWidget:
        page, layout = self._scrollable_page()

        # Header row
        header_row = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("TitleLabel")
        header_row.addWidget(title)
        header_row.addStretch()

        self._start_stop_btn = QPushButton("▶  Start Scanning")
        self._start_stop_btn.setObjectName("StartButton")
        self._start_stop_btn.setMinimumWidth(160)
        self._start_stop_btn.clicked.connect(self._toggle_scanning)
        header_row.addWidget(self._start_stop_btn)

        layout.addLayout(header_row)

        subtitle = QLabel("F8 — toggle scan   ·   F9 — emergency stop")
        subtitle.setObjectName("SubtitleLabel")
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # Stat cards
        stats_row = QHBoxLayout()
        self._stat_scans = self._make_stat_card("0.0", "SCANS / SEC")
        self._stat_matches = self._make_stat_card("0", "TOTAL MATCHES")
        self._stat_uptime = self._make_stat_card("00:00", "UPTIME")
        self._stat_triggers = self._make_stat_card(
            str(len(self._config.get_triggers())), "ACTIVE TRIGGERS"
        )
        for card in [self._stat_scans, self._stat_matches, self._stat_uptime, self._stat_triggers]:
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        layout.addSpacing(8)

        # Region selector panel
        region_panel = self._make_panel("CAPTURE REGION")
        region_layout = QVBoxLayout()

        region_info_row = QHBoxLayout()
        self._region_label = QLabel(self._region_display_text())
        self._region_label.setStyleSheet(f"color: {ACCENT_PRIMARY}; font-weight: 600;")
        region_info_row.addWidget(self._region_label)
        region_info_row.addStretch()

        select_btn = QPushButton("Select Region")
        select_btn.setObjectName("SecondaryButton")
        select_btn.clicked.connect(self._open_region_selector)
        reset_btn = QPushButton("Full Screen")
        reset_btn.setObjectName("SecondaryButton")
        reset_btn.clicked.connect(self._reset_region)
        region_info_row.addWidget(select_btn)
        region_info_row.addWidget(reset_btn)
        region_layout.addLayout(region_info_row)
        region_panel.layout().addLayout(region_layout)
        layout.addWidget(region_panel)

        # OCR Live preview
        ocr_panel = self._make_panel("LIVE OCR PREVIEW")
        self._ocr_preview = QTextEdit()
        self._ocr_preview.setObjectName("OcrPreview")
        self._ocr_preview.setReadOnly(True)
        self._ocr_preview.setMaximumHeight(120)
        self._ocr_preview.setPlaceholderText("OCR output will appear here when scanning…")
        ocr_panel.layout().addWidget(self._ocr_preview)

        conf_row = QHBoxLayout()
        conf_lbl = QLabel("Confidence:")
        conf_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        self._conf_label = QLabel("0%")
        self._conf_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        conf_row.addWidget(conf_lbl)
        conf_row.addWidget(self._conf_label)
        conf_row.addStretch()
        ocr_panel.layout().addLayout(conf_row)
        layout.addWidget(ocr_panel)

        layout.addStretch()
        return page

    # ── Triggers page ────────────────────────────────────────────────── #

    def _build_triggers_page(self) -> QWidget:
        page, layout = self._scrollable_page()

        header_row = QHBoxLayout()
        title = QLabel("Triggers")
        title.setObjectName("TitleLabel")
        header_row.addWidget(title)
        header_row.addStretch()

        add_btn = QPushButton("＋  New Trigger")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self._add_trigger)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        subtitle = QLabel("Configure text patterns and the keyboard actions they trigger.")
        subtitle.setObjectName("SubtitleLabel")
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        # Trigger table
        self._trigger_table = QTableWidget()
        self._trigger_table.setColumnCount(6)
        self._trigger_table.setHorizontalHeaderLabels(
            ["Name", "Trigger Text", "Match", "Action", "Cooldown", "Actions"]
        )
        self._trigger_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._trigger_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._trigger_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._trigger_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._trigger_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._trigger_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._trigger_table.setColumnWidth(5, 160)
        self._trigger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._trigger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._trigger_table.verticalHeader().setVisible(False)
        self._trigger_table.setShowGrid(False)
        self._trigger_table.setAlternatingRowColors(False)
        layout.addWidget(self._trigger_table)

        self._refresh_trigger_table()
        layout.addStretch()
        return page

    # ── Logs page ────────────────────────────────────────────────────── #

    def _build_logs_page(self) -> QWidget:
        page, layout = self._scrollable_page()

        header_row = QHBoxLayout()
        title = QLabel("Activity Log")
        title.setObjectName("TitleLabel")
        header_row.addWidget(title)
        header_row.addStretch()

        clear_btn = QPushButton("Clear Log")
        clear_btn.setObjectName("SecondaryButton")
        clear_btn.clicked.connect(self._clear_log)
        header_row.addWidget(clear_btn)
        layout.addLayout(header_row)

        subtitle = QLabel("Detected text, matched triggers, and executed actions.")
        subtitle.setObjectName("SubtitleLabel")
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        self._log_view = QTextEdit()
        self._log_view.setObjectName("LogView")
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._log_view, 1)
        return page

    # ── Settings page ────────────────────────────────────────────────── #

    def _build_settings_page(self) -> QWidget:
        from PySide6.QtWidgets import QLineEdit

        page, layout = self._scrollable_page()

        title = QLabel("Settings")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        layout.addSpacing(8)

        # ── Scan settings ────────────────────────────────────────────── #
        scan_panel = self._make_panel("SCAN SETTINGS")
        scan_form = QVBoxLayout()

        interval_row = QHBoxLayout()
        interval_lbl = QLabel("Scan interval (ms):")
        interval_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(100, 10000)
        self._interval_spin.setValue(self._config.get("scan_interval", 300))
        self._interval_spin.setSuffix(" ms")
        self._interval_spin.setFixedWidth(120)
        self._interval_spin.valueChanged.connect(
            lambda v: self._config.set("scan_interval", v)
        )
        interval_row.addWidget(interval_lbl)
        interval_row.addWidget(self._interval_spin)
        interval_row.addStretch()
        scan_form.addLayout(interval_row)

        # Confidence threshold — default lowered to 30 for game compatibility
        conf_row = QHBoxLayout()
        conf_lbl = QLabel("OCR confidence threshold:")
        conf_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        conf_lbl.setToolTip(
            "Minimum Tesseract word confidence to accept.\n"
            "Desktop apps: 50-70.  Game / FFXI chat: 20-35.\n"
            "Default is now 30 to avoid silently dropping game text."
        )
        self._conf_slider = QSlider(Qt.Orientation.Horizontal)
        self._conf_slider.setRange(0, 100)
        self._conf_slider.setValue(self._config.get("ocr_confidence_threshold", 30))
        self._conf_slider.setFixedWidth(200)
        self._conf_slider_label = QLabel(f"{self._conf_slider.value()}%")
        self._conf_slider_label.setStyleSheet(
            f"color: {ACCENT_PRIMARY}; font-weight: 600; min-width: 36px;"
        )
        self._conf_slider.valueChanged.connect(self._on_conf_slider_changed)
        conf_row.addWidget(conf_lbl)
        conf_row.addWidget(self._conf_slider)
        conf_row.addWidget(self._conf_slider_label)
        conf_row.addStretch()
        scan_form.addLayout(conf_row)

        scan_panel.layout().addLayout(scan_form)
        layout.addWidget(scan_panel)

        # ── OCR preprocessing mode ───────────────────────────────────── #
        preproc_panel = self._make_panel("IMAGE PREPROCESSING MODE")
        preproc_layout = QVBoxLayout()

        preproc_hint = QLabel(
            "Auto — detects dark/light background per frame (recommended).\n"
            "Light — dark text on bright background (Notepad, browser, Telegram).\n"
            "Game — coloured/white text on dark background (FFXI, MMO chat logs).\n\n"
            "If OCR works on desktop apps but produces garbage on FFXI, set this to Game."
        )
        preproc_hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        preproc_hint.setWordWrap(True)
        preproc_layout.addWidget(preproc_hint)

        preproc_row = QHBoxLayout()
        preproc_lbl = QLabel("Preprocessing mode:")
        preproc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._preproc_combo = QComboBox()
        self._preproc_combo.addItems(["auto", "light", "game"])
        saved_mode = self._config.get("preprocess_mode", "auto")
        idx = self._preproc_combo.findText(saved_mode)
        if idx >= 0:
            self._preproc_combo.setCurrentIndex(idx)
        self._preproc_combo.currentTextChanged.connect(self._on_preproc_mode_changed)
        preproc_row.addWidget(preproc_lbl)
        preproc_row.addWidget(self._preproc_combo)
        preproc_row.addStretch()
        preproc_layout.addLayout(preproc_row)
        preproc_panel.layout().addLayout(preproc_layout)
        layout.addWidget(preproc_panel)

        # ── Tesseract OCR settings ───────────────────────────────────── #
        tess_panel = self._make_panel("TESSERACT OCR")
        tess_layout = QVBoxLayout()

        tess_hint = QLabel(
            "Tesseract must be installed separately.\n"
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "Add Tesseract to PATH or enter the executable path below."
        )
        tess_hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        tess_hint.setWordWrap(True)
        tess_layout.addWidget(tess_hint)

        tess_path_row = QHBoxLayout()
        tess_path_lbl = QLabel("Tesseract path (optional):")
        tess_path_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._tess_path_edit = QLineEdit()
        self._tess_path_edit.setPlaceholderText(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self._tess_path_edit.setText(self._config.get("tesseract_cmd", ""))
        self._tess_path_edit.textChanged.connect(self._on_tess_path_changed)
        tess_path_row.addWidget(tess_path_lbl)
        tess_path_row.addWidget(self._tess_path_edit, 1)
        tess_layout.addLayout(tess_path_row)

        # PSM (Page Segmentation Mode) selector
        psm_row = QHBoxLayout()
        psm_lbl = QLabel("Page segmentation (PSM):")
        psm_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        psm_lbl.setToolTip(
            "PSM 11 Sparse — best for full-screen / game HUD (DEFAULT).\n"
            "PSM 6 Block  — best for a tightly-cropped chat box region.\n"
            "PSM 7 Line   — single line, for narrow status bars.\n\n"
            "PSM 6 with a full-screen game capture is a common cause of\n"
            "garbage output — the layout analyser mis-segments the HUD."
        )
        self._psm_combo = QComboBox()
        self._psm_combo.addItems([
            "PSM 11 — Sparse text (game / full-screen)  [recommended]",
            "PSM 6  — Uniform text block (cropped chat box)",
            "PSM 7  — Single line",
        ])
        psm_map = {
            "--psm 11 --oem 3": 0,
            "--psm 6 --oem 3": 1,
            "--psm 7 --oem 3": 2,
        }
        saved_cfg = self._config.get("tesseract_config", "--psm 11 --oem 3")
        self._psm_combo.setCurrentIndex(psm_map.get(saved_cfg, 0))
        self._psm_combo.currentIndexChanged.connect(self._on_psm_changed)
        psm_row.addWidget(psm_lbl)
        psm_row.addWidget(self._psm_combo, 1)
        tess_layout.addLayout(psm_row)

        tess_panel.layout().addLayout(tess_layout)
        layout.addWidget(tess_panel)

        # ── DPI / Debug diagnostics ──────────────────────────────────── #
        diag_panel = self._make_panel("DIAGNOSTICS")
        diag_layout = QVBoxLayout()

        dpi_scale = get_dpi_scale()
        dpi_info = QLabel(
            f"Detected DPI scale: {dpi_scale:.2f}×  ({int(dpi_scale * 96)} DPI)\n"
            "If DPI scale > 1.0, region coordinates are automatically converted from\n"
            "logical (Qt) pixels to physical pixels before capture. This fixes\n"
            "the common issue where the region selector crops the wrong area on\n"
            "125% / 150% / 200% scaled displays."
        )
        dpi_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        dpi_info.setWordWrap(True)
        diag_layout.addWidget(dpi_info)

        debug_row = QHBoxLayout()
        debug_hint = QLabel(
            "Save a single raw + processed debug frame to debug_frames/ to verify\n"
            "what the capture and preprocessing pipeline actually produces:"
        )
        debug_hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        debug_hint.setWordWrap(True)

        debug_btn = QPushButton("Save Debug Frame")
        debug_btn.setObjectName("SecondaryButton")
        debug_btn.setToolTip(
            "Saves debug_frames/debug_raw.png and debug_frames/debug_processed.png.\n"
            "Open these to verify:\n"
            "  raw.png     — is the correct area being captured?\n"
            "  processed.png — is the text legible after preprocessing?"
        )
        debug_btn.clicked.connect(self._save_debug_frame)
        self._debug_path_label = QLabel("")
        self._debug_path_label.setStyleSheet(f"color: {ACCENT_PRIMARY}; font-size: 11px;")

        debug_row.addWidget(debug_btn)
        debug_row.addWidget(self._debug_path_label, 1)
        diag_layout.addWidget(debug_hint)
        diag_layout.addLayout(debug_row)

        diag_panel.layout().addLayout(diag_layout)
        layout.addWidget(diag_panel)

        # ── Profiles ─────────────────────────────────────────────────── #
        profile_panel = self._make_panel("PROFILES")
        profile_layout = QVBoxLayout()
        profile_hint = QLabel("Save and load complete trigger profiles (JSON files in /profiles/).")
        profile_hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        profile_layout.addWidget(profile_hint)

        profile_row = QHBoxLayout()
        self._profile_name_edit = QLineEdit()
        self._profile_name_edit.setPlaceholderText("Profile name…")
        self._profile_name_edit.setFixedWidth(200)
        save_profile_btn = QPushButton("Save Profile")
        save_profile_btn.setObjectName("SecondaryButton")
        save_profile_btn.clicked.connect(self._save_profile)

        self._profile_combo = QComboBox()
        self._refresh_profile_combo()
        load_profile_btn = QPushButton("Load Profile")
        load_profile_btn.setObjectName("SecondaryButton")
        load_profile_btn.clicked.connect(self._load_profile)

        profile_row.addWidget(self._profile_name_edit)
        profile_row.addWidget(save_profile_btn)
        profile_row.addSpacing(20)
        profile_row.addWidget(self._profile_combo)
        profile_row.addWidget(load_profile_btn)
        profile_row.addStretch()
        profile_layout.addLayout(profile_row)
        profile_panel.layout().addLayout(profile_layout)
        layout.addWidget(profile_panel)

        layout.addStretch()
        return page

    # ================================================================== #
    # UI Helpers                                                           #
    # ================================================================== #

    @staticmethod
    def _scrollable_page():
        """
        Return (outer_widget, inner_layout).

        outer_widget  — the QWidget to add to the QStackedWidget.
        inner_layout  — the QVBoxLayout inside the scroll area; callers
                        append their content widgets here directly.

        Why the old design crashed
        --------------------------
        The previous version returned `inner` (the scroll child) directly
        and expected callers to recover the layout via findChild(QVBoxLayout).
        In PySide6, findChild returns a plain Python wrapper with no extra
        reference count.  As soon as the call expression ended the wrapper was
        eligible for garbage collection, leaving a dangling C++ pointer.  The
        next access raised RuntimeError: Internal C++ object already deleted.

        Returning the layout as a second value keeps a live Python reference
        for the entire lifetime of the calling method, which is all that is
        needed.
        """
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(28, 24, 28, 24)
        inner_layout.setSpacing(12)

        scroll.setWidget(inner)
        outer_layout.addWidget(scroll)

        return outer, inner_layout

    @staticmethod
    def _make_panel(title: str = "") -> QWidget:
        panel = QWidget()
        panel.setObjectName("Panel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("SectionLabel")
            v.addWidget(lbl)
        return panel

    def _make_stat_card(self, value: str, label: str) -> QWidget:
        card = QWidget()
        card.setObjectName("StatCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(4)
        val_lbl = QLabel(value)
        val_lbl.setObjectName("StatValue")
        lab_lbl = QLabel(label)
        lab_lbl.setObjectName("StatLabel")
        v.addWidget(val_lbl)
        v.addWidget(lab_lbl)
        # Store reference on card for updates
        card._val_label = val_lbl  # type: ignore[attr-defined]
        return card

    @staticmethod
    def _stat_set(card: QWidget, value: str) -> None:
        card._val_label.setText(value)  # type: ignore[attr-defined]

    def _region_display_text(self) -> str:
        r = self._config.get_region()
        if r:
            return f"Custom: {r[0]},{r[1]}  {r[2]}×{r[3]}"
        return "Full Screen (primary monitor)"

    # ================================================================== #
    # Navigation                                                           #
    # ================================================================== #

    def _nav_to(self, index: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._stack.setCurrentIndex(index)
        self._active_nav_index = index

    # ================================================================== #
    # Scanning                                                             #
    # ================================================================== #

    def _toggle_scanning(self) -> None:
        if self._scanning:
            self._stop_scanning()
        else:
            self._start_scanning()

    def _start_scanning(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._stop_event.clear()
        self._start_time = time.monotonic()
        self._scan_count = 0
        self._scan_count_window = 0
        self._last_stats_time = time.monotonic()

        self._trigger_engine.set_triggers(self._config.get_triggers())
        self._trigger_engine.enabled = True

        self._scan_thread = Thread(target=self._scan_loop, name="OcrScanLoop", daemon=True)
        self._scan_thread.start()

        self._start_stop_btn.setText("■  Stop Scanning")
        self._start_stop_btn.setObjectName("StopButton")
        self._start_stop_btn.style().unpolish(self._start_stop_btn)
        self._start_stop_btn.style().polish(self._start_stop_btn)

        self._set_status("running", "Running")
        self._log("system", "Scanning started")
        logger.info("Scanning started")

    def _stop_scanning(self) -> None:
        if not self._scanning:
            return
        self._scanning = False
        self._stop_event.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=3)

        self._start_stop_btn.setText("▶  Start Scanning")
        self._start_stop_btn.setObjectName("StartButton")
        self._start_stop_btn.style().unpolish(self._start_stop_btn)
        self._start_stop_btn.style().polish(self._start_stop_btn)

        self._set_status("stopped", "Stopped")
        self._log("system", "Scanning stopped")
        logger.info("Scanning stopped")

    def _scan_loop(self) -> None:
        """Background thread: capture → OCR → match → execute."""
        capture = ScreenCapture()
        # Copy preprocess mode from the shared instance so settings changes
        # that happen while scanning are picked up on the next loop tick.
        capture.open()
        scan_interval_s = self._config.get("scan_interval", 300) / 1000.0

        try:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()

                # Re-read config every loop so interval/region changes apply live
                scan_interval_s = self._config.get("scan_interval", 300) / 1000.0
                region = self._config.get_region()

                # Sync preprocess mode from the main-thread capture instance
                capture.preprocess_mode = self._capture.preprocess_mode

                raw = capture.capture(region)
                if raw is None:
                    time.sleep(0.1)
                    continue

                processed = ScreenCapture.preprocess(raw, mode=capture.preprocess_mode)
                result: OcrResult = self._ocr.run(processed)

                self._scan_count += 1
                self._scan_count_window += 1

                # Emit OCR result to UI
                self._signals.ocr_result.emit(result.raw_text, result.avg_confidence)

                if result.success:
                    matches = self._trigger_engine.evaluate(result.raw_text)
                    for match in matches:
                        self._total_matches += 1
                        action_str = self._action_to_display(match.action)
                        self._signals.trigger_matched.emit(
                            match.trigger_name, match.matched_text[:80], action_str
                        )
                        self._executor.execute(match.action)

                # Stats every second
                now = time.monotonic()
                elapsed = now - self._last_stats_time
                if elapsed >= 1.0:
                    sps = self._scan_count_window / elapsed
                    self._signals.scan_stats.emit(sps, self._total_matches)
                    self._scan_count_window = 0
                    self._last_stats_time = now

                # Sleep for remainder of interval
                loop_elapsed = time.monotonic() - loop_start
                sleep_time = max(0.0, scan_interval_s - loop_elapsed)
                if sleep_time > 0:
                    self._stop_event.wait(timeout=sleep_time)

        except Exception as exc:
            logger.error("Scan loop crashed: %s", exc, exc_info=True)
            self._signals.error_occurred.emit(str(exc))
        finally:
            capture.close()

    # ================================================================== #
    # Signal handlers (UI thread)                                          #
    # ================================================================== #

    def _connect_signals(self) -> None:
        self._signals.ocr_result.connect(self._on_ocr_result)
        self._signals.trigger_matched.connect(self._on_trigger_matched)
        self._signals.scan_stats.connect(self._on_scan_stats)
        self._signals.error_occurred.connect(self._on_error)

    @Slot(str, float)
    def _on_ocr_result(self, text: str, confidence: float) -> None:
        display = text.strip() if text.strip() else "(no text detected)"
        self._ocr_preview.setPlainText(display)
        self._conf_label.setText(f"{confidence:.0f}%")

    @Slot(str, str, str)
    def _on_trigger_matched(self, trigger_name: str, matched_text: str, action_str: str) -> None:
        self._log("match", f"[{trigger_name}]  →  {action_str}  |  \"{matched_text}\"")
        self._stat_set(self._stat_matches, str(self._total_matches))

    @Slot(float, int)
    def _on_scan_stats(self, sps: float, total: int) -> None:
        self._stat_set(self._stat_scans, f"{sps:.1f}")
        self._stat_set(self._stat_matches, str(total))

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._log("error", f"Error: {message}")
        self._stop_scanning()

    def _update_uptime(self) -> None:
        if self._scanning and self._start_time:
            elapsed = int(time.monotonic() - self._start_time)
            minutes, seconds = divmod(elapsed, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                display = f"{minutes:02d}:{seconds:02d}"
            self._stat_set(self._stat_uptime, display)

    # ================================================================== #
    # Trigger table                                                        #
    # ================================================================== #

    def _refresh_trigger_table(self) -> None:
        triggers = self._config.get_triggers()
        self._trigger_table.setRowCount(len(triggers))

        for row, t in enumerate(triggers):
            action = t.get("action", {})

            name_item = QTableWidgetItem(t.get("name", t.get("trigger", "")))
            name_item.setData(Qt.ItemDataRole.UserRole, t.get("id"))

            trigger_item = QTableWidgetItem(t.get("trigger", ""))
            trigger_item.setToolTip(t.get("trigger", ""))

            match_item = QTableWidgetItem(t.get("match_type", "contains"))
            action_item = QTableWidgetItem(self._action_to_display(action))
            cooldown_item = QTableWidgetItem(f"{t.get('cooldown', 3)}s")

            for item in [name_item, trigger_item, match_item, action_item, cooldown_item]:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            # Enabled badge
            enabled = t.get("enabled", True)
            badge = QLabel("● ON" if enabled else "● OFF")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(ENABLED_BADGE if enabled else DISABLED_BADGE)

            self._trigger_table.setItem(row, 0, name_item)
            self._trigger_table.setItem(row, 1, trigger_item)
            self._trigger_table.setItem(row, 2, match_item)
            self._trigger_table.setItem(row, 3, action_item)
            self._trigger_table.setItem(row, 4, cooldown_item)

            # Action buttons cell
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)

            edit_btn = QPushButton("Edit")
            edit_btn.setObjectName("SecondaryButton")
            edit_btn.setFixedHeight(26)
            edit_btn.clicked.connect(lambda checked, tid=t["id"]: self._edit_trigger(tid))

            del_btn = QPushButton("Delete")
            del_btn.setObjectName("DangerButton")
            del_btn.setFixedHeight(26)
            del_btn.clicked.connect(lambda checked, tid=t["id"]: self._delete_trigger(tid))

            toggle_btn = QPushButton("Disable" if enabled else "Enable")
            toggle_btn.setObjectName("SecondaryButton")
            toggle_btn.setFixedHeight(26)
            toggle_btn.clicked.connect(lambda checked, tid=t["id"]: self._toggle_trigger(tid))

            btn_layout.addWidget(toggle_btn)
            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(del_btn)

            self._trigger_table.setCellWidget(row, 5, btn_widget)
            self._trigger_table.setRowHeight(row, 46)

        self._stat_set(
            self._stat_triggers,
            str(sum(1 for t in triggers if t.get("enabled", True)))
        )

    def _add_trigger(self) -> None:
        dlg = TriggerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            trigger = dlg.get_trigger()
            if trigger:
                self._config.add_trigger(trigger)
                self._trigger_engine.set_triggers(self._config.get_triggers())
                self._refresh_trigger_table()
                self._log("system", f"Trigger added: {trigger['name']}")

    def _edit_trigger(self, trigger_id: str) -> None:
        existing = self._config.get_trigger_by_id(trigger_id)
        if not existing:
            return
        dlg = TriggerDialog(self, trigger=existing)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_trigger()
            if updated:
                self._config.update_trigger(trigger_id, updated)
                self._trigger_engine.set_triggers(self._config.get_triggers())
                self._refresh_trigger_table()
                self._log("system", f"Trigger updated: {updated['name']}")

    def _delete_trigger(self, trigger_id: str) -> None:
        existing = self._config.get_trigger_by_id(trigger_id)
        name = existing.get("name", trigger_id) if existing else trigger_id
        reply = QMessageBox.question(
            self, "Delete Trigger",
            f"Delete trigger \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._config.delete_trigger(trigger_id)
            self._trigger_engine.set_triggers(self._config.get_triggers())
            self._refresh_trigger_table()
            self._log("system", f"Trigger deleted: {name}")

    def _toggle_trigger(self, trigger_id: str) -> None:
        existing = self._config.get_trigger_by_id(trigger_id)
        if not existing:
            return
        updated = dict(existing)
        updated["enabled"] = not updated.get("enabled", True)
        self._config.update_trigger(trigger_id, updated)
        self._trigger_engine.set_triggers(self._config.get_triggers())
        self._refresh_trigger_table()

    # ================================================================== #
    # Region selection                                                     #
    # ================================================================== #

    def _open_region_selector(self) -> None:
        self.hide()
        QTimer.singleShot(300, self._show_selector)

    def _show_selector(self) -> None:
        selector = RegionSelector()
        selector.region_selected.connect(self._on_region_selected)
        selector.cancelled.connect(self._on_region_cancelled)
        selector.showFullScreen()

    @Slot(list)
    def _on_region_selected(self, region: list) -> None:
        self._config.set_region(region)
        self._region_label.setText(self._region_display_text())
        self._log("system", f"Capture region set: {region}")
        self.show()

    @Slot()
    def _on_region_cancelled(self) -> None:
        self.show()

    def _reset_region(self) -> None:
        self._config.set_region(None)
        self._region_label.setText(self._region_display_text())
        self._log("system", "Capture region reset to full screen")

    # ================================================================== #
    # Settings handlers                                                    #
    # ================================================================== #

    def _on_conf_slider_changed(self, value: int) -> None:
        self._conf_slider_label.setText(f"{value}%")
        self._ocr.set_confidence_threshold(value)
        self._config.set("ocr_confidence_threshold", value)

    def _on_tess_path_changed(self, path: str) -> None:
        self._config.set("tesseract_cmd", path)
        if path.strip():
            self._ocr.set_tesseract_cmd(path.strip())

    def _on_preproc_mode_changed(self, mode: str) -> None:
        """Update preprocessing mode on both the main capture instance and config."""
        self._capture.preprocess_mode = mode
        self._config.set("preprocess_mode", mode)
        self._log("system", f"Preprocessing mode changed to: {mode}")

    def _on_psm_changed(self, index: int) -> None:
        """Map combo index back to tesseract config string."""
        psm_configs = [
            "--psm 11 --oem 3",  # 0 — sparse (default, game-safe)
            "--psm 6 --oem 3",   # 1 — uniform block (cropped chat)
            "--psm 7 --oem 3",   # 2 — single line
        ]
        if 0 <= index < len(psm_configs):
            cfg = psm_configs[index]
            self._ocr.set_tesseract_config(cfg)
            self._config.set("tesseract_config", cfg)
            self._log("system", f"Tesseract PSM changed to: {cfg}")

    def _save_debug_frame(self) -> None:
        """Capture one frame, save raw+processed PNGs, show path in UI."""
        region = self._config.get_region()
        path = self._capture.save_single_debug_frame(region)
        if path:
            self._debug_path_label.setText(f"Saved → {path}")
            self._log("system", f"Debug frame saved: {path}")
        else:
            self._debug_path_label.setText("Capture failed — is a monitor connected?")
            self._log("error", "Debug frame capture failed")

    def _save_profile(self) -> None:
        name = self._profile_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Profile", "Enter a profile name.")
            return
        if self._config.save_profile(name):
            self._log("system", f"Profile saved: {name}")
            self._refresh_profile_combo()
        else:
            QMessageBox.warning(self, "Profile", f"Failed to save profile '{name}'.")

    def _load_profile(self) -> None:
        name = self._profile_combo.currentText()
        if not name:
            return
        if self._config.load_profile(name):
            self._trigger_engine.set_triggers(self._config.get_triggers())
            self._refresh_trigger_table()
            self._log("system", f"Profile loaded: {name}")
        else:
            QMessageBox.warning(self, "Profile", f"Failed to load profile '{name}'.")

    def _refresh_profile_combo(self) -> None:
        self._profile_combo.clear()
        self._profile_combo.addItems(self._config.list_profiles())

    # ================================================================== #
    # Logging                                                              #
    # ================================================================== #

    def _log(self, level: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {
            "match": ACCENT_PRIMARY,
            "error": ACCENT_DANGER,
            "system": ACCENT_WARNING,
        }
        color = colors.get(level, TEXT_SECONDARY)
        prefix = {"match": "MATCH", "error": "ERROR", "system": "SYS"}.get(level, "INFO")
        html = (
            f'<span style="color:{TEXT_MUTED}">{ts}</span> '
            f'<span style="color:{color};font-weight:600">[{prefix}]</span> '
            f'<span style="color:{TEXT_PRIMARY}">{message}</span>'
        )
        self._log_view.append(html)
        # Auto-scroll
        scrollbar = self._log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self) -> None:
        self._log_view.clear()

    # ================================================================== #
    # Global hotkeys                                                       #
    # ================================================================== #

    def _setup_global_hotkeys(self) -> None:
        try:
            keyboard.add_hotkey("f8", self._hotkey_toggle_scan, suppress=False)
            keyboard.add_hotkey("f9", self._hotkey_emergency_stop, suppress=False)
            logger.info("Global hotkeys registered: F8=toggle, F9=stop")
        except Exception as exc:
            logger.warning("Could not register global hotkeys: %s", exc)

    def _hotkey_toggle_scan(self) -> None:
        # keyboard callbacks run in a separate thread — use QTimer to hop to UI thread
        QTimer.singleShot(0, self._toggle_scanning)

    def _hotkey_emergency_stop(self) -> None:
        QTimer.singleShot(0, self._emergency_stop)

    def _emergency_stop(self) -> None:
        self._executor.clear_queue()
        self._stop_scanning()
        self._log("system", "Emergency stop activated (F9)")

    # ================================================================== #
    # System Tray                                                          #
    # ================================================================== #

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray not available")
            return

        self._tray = QSystemTrayIcon(self)
        # Use a simple coloured icon from built-in Qt icons
        self._tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        self._tray.setToolTip("Screen Trigger Macro")

        from PySide6.QtWidgets import QMenu
        tray_menu = QMenu()

        toggle_scan_action = QAction("Toggle Scanning (F8)", self)
        toggle_scan_action.triggered.connect(self._toggle_scanning)

        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)

        tray_menu.addAction(toggle_scan_action)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    # ================================================================== #
    # Helpers                                                              #
    # ================================================================== #

    def _set_status(self, status: str, text: str) -> None:
        self._status_dot.setProperty("status", status)
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self._status_label.setText(text)

    @staticmethod
    def _action_to_display(action: dict) -> str:
        a_type = action.get("type", "hotkey")

        if a_type == "hotkey":
            keys = action.get("keys", [])
            return "+".join(k.upper() for k in keys) or "(no keys)"

        elif a_type == "text":
            raw = action.get("text", "")
            # Show up to 40 chars; replace newlines with ↵ for readability
            preview = raw.replace("\n", " ↵ ").replace("\r", "")
            return f'"{preview[:40]}{"…" if len(preview) > 40 else ""}"'

        elif a_type == "sequence":
            steps = action.get("sequence", [])
            parts: list[str] = []
            for s in steps[:3]:
                st = s.get("type")
                if st == "hotkey":
                    parts.append("+".join(k.upper() for k in s.get("keys", [])))
                elif st == "key":
                    parts.append(f"[{s.get('key', '')}]")
                elif st == "text":
                    t = s.get("text", "")
                    parts.append(f'"{t[:15]}{"…" if len(t) > 15 else ""}"')
                elif st == "delay":
                    parts.append(f"wait {s.get('ms', 0)}ms")
            suffix = f" +{len(steps) - 3} more" if len(steps) > 3 else ""
            return " → ".join(parts) + suffix

        return str(action)

    # ================================================================== #
    # Window lifecycle                                                     #
    # ================================================================== #

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_scanning()
        self._executor.stop()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self._config.save()
        event.accept()
