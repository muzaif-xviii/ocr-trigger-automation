"""
styles.py
Cyberpunk / MMO-overlay dark theme for PySide6.
Uses a deep navy/charcoal base with electric violet and cyan accents.
Font: Segoe UI on Windows, system-ui fallback elsewhere.
"""

ACCENT_PRIMARY = "#7c3aed"   # Electric violet
ACCENT_SECONDARY = "#06b6d4"  # Cyan
ACCENT_DANGER = "#ef4444"    # Red
ACCENT_SUCCESS = "#10b981"   # Emerald
ACCENT_WARNING = "#f59e0b"   # Amber

BG_BASE = "#0a0b14"
BG_SURFACE = "#111827"
BG_PANEL = "#1a1f2e"
BG_ELEVATED = "#232b3e"
BG_HOVER = "#2a3347"

TEXT_PRIMARY = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#475569"

BORDER_DEFAULT = "#2d3748"
BORDER_ACCENT = "#4c1d95"

SIDEBAR_WIDTH = 220

STYLESHEET = f"""
/* ── Base ── */
QMainWindow, QWidget {{
    background-color: {BG_BASE};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "SF Pro Display", system-ui, sans-serif;
    font-size: 13px;
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: {BG_SURFACE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {ACCENT_PRIMARY};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: #9c5cf8;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_SURFACE};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {ACCENT_PRIMARY};
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Sidebar ── */
#Sidebar {{
    background-color: {BG_SURFACE};
    border-right: 1px solid {BORDER_DEFAULT};
    min-width: {SIDEBAR_WIDTH}px;
    max-width: {SIDEBAR_WIDTH}px;
}}

/* ── Sidebar nav buttons ── */
#NavButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {TEXT_SECONDARY};
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
#NavButton:hover {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
}}
#NavButton[active="true"] {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {BORDER_ACCENT}, stop:1 transparent
    );
    color: {TEXT_PRIMARY};
    border-left: 3px solid {ACCENT_PRIMARY};
}}

/* ── Content area ── */
#ContentArea {{
    background-color: {BG_BASE};
}}

/* ── Panels / cards ── */
#Panel {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 12px;
    padding: 16px;
}}

/* ── Labels ── */
#TitleLabel {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    letter-spacing: -0.5px;
}}
#SectionLabel {{
    font-size: 11px;
    font-weight: 600;
    color: {TEXT_MUTED};
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
#SubtitleLabel {{
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}

/* ── Stat cards ── */
#StatCard {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 {BG_ELEVATED}, stop:1 {BG_PANEL}
    );
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 10px;
    padding: 14px;
}}
#StatValue {{
    font-size: 28px;
    font-weight: 700;
    color: {ACCENT_SECONDARY};
}}
#StatLabel {{
    font-size: 11px;
    color: {TEXT_MUTED};
    letter-spacing: 0.8px;
}}

/* ── Primary button ── */
#PrimaryButton {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_PRIMARY}, stop:1 #5b21b6
    );
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 20px;
    font-weight: 600;
    font-size: 13px;
}}
#PrimaryButton:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #9c5cf8, stop:1 {ACCENT_PRIMARY}
    );
}}
#PrimaryButton:pressed {{
    background: #5b21b6;
}}
#PrimaryButton:disabled {{
    background: {BG_ELEVATED};
    color: {TEXT_MUTED};
}}

/* ── Danger button ── */
#DangerButton {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_DANGER}, stop:1 #b91c1c
    );
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 20px;
    font-weight: 600;
    font-size: 13px;
}}
#DangerButton:hover {{
    background: #f87171;
}}
#DangerButton:pressed {{
    background: #991b1b;
}}

/* ── Secondary button ── */
#SecondaryButton {{
    background: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 500;
}}
#SecondaryButton:hover {{
    background: {BG_HOVER};
    border-color: {ACCENT_PRIMARY};
}}
#SecondaryButton:pressed {{
    background: {BG_ELEVATED};
}}

/* ── Start/Stop toggle ── */
#StartButton {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #065f46, stop:1 #059669
    );
    color: white;
    border: none;
    border-radius: 10px;
    padding: 12px 28px;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
#StartButton:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #059669, stop:1 #10b981
    );
}}
#StopButton {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #7f1d1d, stop:1 {ACCENT_DANGER}
    );
    color: white;
    border: none;
    border-radius: 10px;
    padding: 12px 28px;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
#StopButton:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_DANGER}, stop:1 #f87171
    );
}}

/* ── Input fields ── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 7px 10px;
    selection-background-color: {ACCENT_PRIMARY};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT_PRIMARY};
    outline: none;
}}
QLineEdit:disabled {{
    background-color: {BG_SURFACE};
    color: {TEXT_MUTED};
}}

/* ── ComboBox ── */
QComboBox {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 7px 10px;
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: {ACCENT_PRIMARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {TEXT_SECONDARY};
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY};
    padding: 4px;
}}

/* ── SpinBox ── */
QSpinBox, QDoubleSpinBox {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 7px 8px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT_PRIMARY};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {BG_HOVER};
    border: none;
    width: 18px;
}}

/* ── Slider ── */
QSlider::groove:horizontal {{
    background: {BG_ELEVATED};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT_PRIMARY};
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_PRIMARY}, stop:1 {ACCENT_SECONDARY}
    );
    border-radius: 3px;
}}

/* ── CheckBox ── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER_DEFAULT};
    background: {BG_ELEVATED};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_PRIMARY};
    border-color: {ACCENT_PRIMARY};
    image: none;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT_PRIMARY};
}}

/* ── Table ── */
QTableWidget {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 8px;
    gridline-color: {BORDER_DEFAULT};
    color: {TEXT_PRIMARY};
    selection-background-color: {BORDER_ACCENT};
}}
QTableWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {BORDER_DEFAULT};
}}
QTableWidget::item:selected {{
    background-color: {BORDER_ACCENT};
    color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: {BG_ELEVATED};
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {BORDER_DEFAULT};
    text-transform: uppercase;
}}

/* ── Tab bar ── */
QTabWidget::pane {{
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 8px;
    background: {BG_PANEL};
}}
QTabBar::tab {{
    background: {BG_SURFACE};
    color: {TEXT_SECONDARY};
    padding: 8px 20px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT_PRIMARY};
}}
QTabBar::tab:hover {{
    background: {BG_ELEVATED};
}}

/* ── Dialogs ── */
QDialog {{
    background-color: {BG_PANEL};
}}
QDialogButtonBox QPushButton {{
    min-width: 80px;
    padding: 8px 16px;
    border-radius: 6px;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background: {BORDER_DEFAULT};
}}

/* ── ToolTip ── */
QToolTip {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}

/* ── Status indicator dot ── */
#StatusDot[status="running"] {{
    background: {ACCENT_SUCCESS};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}
#StatusDot[status="stopped"] {{
    background: {TEXT_MUTED};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}

/* ── Log text area ── */
#LogView {{
    background-color: {BG_BASE};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 8px;
    color: {TEXT_SECONDARY};
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 8px;
}}

/* ── OCR preview ── */
#OcrPreview {{
    background-color: {BG_BASE};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 8px;
    color: {ACCENT_SECONDARY};
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    padding: 8px;
}}

/* ── Separator ── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {BORDER_DEFAULT};
}}

/* ── GroupBox ── */
QGroupBox {{
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: {TEXT_MUTED};
    text-transform: uppercase;
}}
"""

# Inline badge for trigger status
ENABLED_BADGE = f"""
    background-color: rgba(16, 185, 129, 0.15);
    color: {ACCENT_SUCCESS};
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
"""

DISABLED_BADGE = f"""
    background-color: rgba(71, 85, 105, 0.2);
    color: {TEXT_MUTED};
    border: 1px solid rgba(71, 85, 105, 0.4);
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
"""
