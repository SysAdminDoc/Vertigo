"""Centralized theme tokens, stylesheet generation, and app theme helpers."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemePalette:
    id: str
    label: str
    mode: str  # "dark" | "light"
    base: str
    mantle: str
    crust: str
    surface0: str
    surface1: str
    surface2: str
    overlay0: str
    overlay1: str
    overlay2: str
    subtext0: str
    subtext1: str
    text: str
    accent: str
    accent_soft: str
    accent_muted: str
    accent_hover: str
    accent_selected: str
    accent_text: str
    red: str
    red_soft: str
    yellow: str
    yellow_soft: str
    green: str
    green_soft: str
    pink: str
    focus: str
    scrim: str
    overlay_scrim: str
    hint_bg: str
    hint_text: str


THEMES: dict[str, ThemePalette] = {
    "mocha": ThemePalette(
        id="mocha",
        label="Mocha",
        mode="dark",
        base="#1e1e2e",
        mantle="#181825",
        crust="#11111b",
        surface0="#313244",
        surface1="#45475a",
        surface2="#585b70",
        overlay0="#6c7086",
        overlay1="#7f849c",
        overlay2="#9399b2",
        subtext0="#a6adc8",
        subtext1="#bac2de",
        text="#cdd6f4",
        accent="#cba6f7",
        accent_soft="#b990f2",
        accent_muted="rgba(203, 166, 247, 0.06)",
        accent_hover="rgba(203, 166, 247, 0.08)",
        accent_selected="rgba(203, 166, 247, 0.12)",
        accent_text="#11111b",
        red="#f38ba8",
        red_soft="rgba(243, 139, 168, 0.10)",
        yellow="#f9e2af",
        yellow_soft="rgba(249, 226, 175, 0.08)",
        green="#a6e3a1",
        green_soft="rgba(166, 227, 161, 0.08)",
        pink="#f5c2e7",
        focus="#b4befe",
        scrim="rgba(0, 0, 0, 0.60)",
        overlay_scrim="rgba(0, 0, 0, 0.58)",
        hint_bg="rgba(17, 17, 27, 0.84)",
        hint_text="#cdd6f4",
    ),
    "graphite": ThemePalette(
        id="graphite",
        label="Graphite",
        mode="dark",
        base="#181a20",
        mantle="#121419",
        crust="#0b0d11",
        surface0="#252832",
        surface1="#353946",
        surface2="#4a5060",
        overlay0="#687083",
        overlay1="#858da0",
        overlay2="#a0a8b8",
        subtext0="#b7bfcc",
        subtext1="#d3d8e3",
        text="#eef1f7",
        accent="#8ab4ff",
        accent_soft="#76a3f2",
        accent_muted="rgba(138, 180, 255, 0.07)",
        accent_hover="rgba(138, 180, 255, 0.10)",
        accent_selected="rgba(138, 180, 255, 0.16)",
        accent_text="#07111f",
        red="#ff7a90",
        red_soft="rgba(255, 122, 144, 0.11)",
        yellow="#ffd166",
        yellow_soft="rgba(255, 209, 102, 0.09)",
        green="#76d391",
        green_soft="rgba(118, 211, 145, 0.09)",
        pink="#c7a6ff",
        focus="#b9d3ff",
        scrim="rgba(0, 0, 0, 0.58)",
        overlay_scrim="rgba(0, 0, 0, 0.56)",
        hint_bg="rgba(11, 13, 17, 0.86)",
        hint_text="#eef1f7",
    ),
    "latte": ThemePalette(
        id="latte",
        label="Latte",
        mode="light",
        base="#f6f7fb",
        mantle="#ffffff",
        crust="#eef1f6",
        surface0="#e7ebf3",
        surface1="#d9deea",
        surface2="#c8cfdd",
        overlay0="#8791a3",
        overlay1="#667086",
        overlay2="#4d576b",
        subtext0="#596376",
        subtext1="#384255",
        text="#172033",
        accent="#7157d9",
        accent_soft="#624bc4",
        accent_muted="rgba(113, 87, 217, 0.07)",
        accent_hover="rgba(113, 87, 217, 0.10)",
        accent_selected="rgba(113, 87, 217, 0.14)",
        accent_text="#ffffff",
        red="#bd2942",
        red_soft="rgba(189, 41, 66, 0.09)",
        yellow="#805b00",
        yellow_soft="rgba(128, 91, 0, 0.08)",
        green="#23784a",
        green_soft="rgba(35, 120, 74, 0.08)",
        pink="#a43f91",
        focus="#4d68d8",
        scrim="rgba(20, 27, 42, 0.38)",
        overlay_scrim="rgba(20, 27, 42, 0.50)",
        hint_bg="rgba(255, 255, 255, 0.92)",
        hint_text="#172033",
    ),
}

DEFAULT_THEME_ID = "mocha"
SYSTEM_THEME_ID = "system"


class Mocha:
    """Compatibility palette for older imports. Prefer current_palette()."""

    base = THEMES["mocha"].base
    mantle = THEMES["mocha"].mantle
    crust = THEMES["mocha"].crust
    surface0 = THEMES["mocha"].surface0
    surface1 = THEMES["mocha"].surface1
    surface2 = THEMES["mocha"].surface2
    overlay0 = THEMES["mocha"].overlay0
    overlay1 = THEMES["mocha"].overlay1
    overlay2 = THEMES["mocha"].overlay2
    subtext0 = THEMES["mocha"].subtext0
    subtext1 = THEMES["mocha"].subtext1
    text = THEMES["mocha"].text
    mauve = THEMES["mocha"].accent
    pink = THEMES["mocha"].pink
    red = THEMES["mocha"].red
    peach = "#fab387"
    yellow = THEMES["mocha"].yellow
    green = THEMES["mocha"].green
    teal = "#94e2d5"
    sky = "#89dceb"
    sapphire = "#74c7ec"
    blue = "#89b4fa"
    lavender = THEMES["mocha"].focus


def theme_choices() -> list[tuple[str, str]]:
    return [(SYSTEM_THEME_ID, "System")] + [(theme.id, theme.label) for theme in THEMES.values()]


def sanitize_theme_preference(preference: str | None) -> str:
    if preference == SYSTEM_THEME_ID:
        return SYSTEM_THEME_ID
    if preference in THEMES:
        return preference
    return SYSTEM_THEME_ID


def resolved_theme_id(preference: str | None = None) -> str:
    pref = sanitize_theme_preference(preference or app_theme_preference())
    if pref != SYSTEM_THEME_ID:
        return pref
    return "mocha" if _system_is_dark() else "latte"


def _system_is_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        pass
    window = app.palette().color(QPalette.ColorRole.Window)
    return window.lightness() < 128


def current_palette() -> ThemePalette:
    app = QApplication.instance()
    if app is not None:
        theme_id = app.property("kilnThemeId")
        if isinstance(theme_id, str) and theme_id in THEMES:
            return THEMES[theme_id]
    return THEMES[resolved_theme_id()]


def app_theme_preference() -> str:
    app = QApplication.instance()
    if app is not None:
        pref = app.property("kilnThemePreference")
        if isinstance(pref, str):
            return sanitize_theme_preference(pref)
    return SYSTEM_THEME_ID


def apply_app_theme(app: QApplication, preference: str | None) -> ThemePalette:
    pref = sanitize_theme_preference(preference)
    theme = THEMES[resolved_theme_id(pref)]
    app.setProperty("kilnThemePreference", pref)
    app.setProperty("kilnThemeId", theme.id)
    app.setPalette(build_qpalette(theme))
    app.setStyleSheet(build_stylesheet(pref))
    return theme


def build_qpalette(theme: ThemePalette) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme.base))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.crust))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.surface0))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.surface0))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.surface0))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(theme.red))
    palette.setColor(QPalette.ColorRole.Link, QColor(theme.accent))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.accent_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.overlay1))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.overlay1))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(theme.overlay1))
    return palette


def to_qcolor(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


def qcolor(hex_or_rgba: str) -> QColor:
    value = hex_or_rgba.strip()
    if value.startswith("rgba(") and value.endswith(")"):
        raw = value[5:-1]
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) == 4:
            r, g, b = (int(float(parts[i])) for i in range(3))
            alpha_raw = float(parts[3])
            alpha = int(alpha_raw * 255) if alpha_raw <= 1 else int(alpha_raw)
            return QColor(r, g, b, max(0, min(255, alpha)))
    return QColor(value)


def build_stylesheet(preference: str | None = None) -> str:
    t = THEMES[resolved_theme_id(preference)]
    return f"""
* {{
    font-family: "Segoe UI", "Inter", system-ui, -apple-system, sans-serif;
    color: {t.text};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}

QMainWindow, QWidget#rootWidget {{
    background: {t.base};
}}

QWidget#titleBar {{
    background: {t.mantle};
    border-bottom: 1px solid {t.surface0};
}}

QLabel#titleText {{
    color: {t.subtext1};
    font-weight: 600;
    letter-spacing: 0px;
}}

QLabel#brand {{
    color: {t.accent};
    font-weight: 800;
    letter-spacing: 0px;
    font-size: 14px;
}}

QLabel#brandDot {{
    color: {t.accent};
    font-size: 16px;
}}

QLabel#titleSep {{
    color: {t.surface2};
}}

QPushButton#winCtl, QPushButton#winClose {{
    background: transparent;
    color: {t.subtext0};
    border: none;
    min-width: 44px;
    min-height: 32px;
    font-size: 14px;
}}
QPushButton#winCtl:hover, QPushButton#winClose:hover {{
    background: {t.surface0};
    color: {t.text};
}}
QPushButton#winClose:hover {{
    background: {t.red};
    color: {t.accent_text};
}}
QPushButton#winCtl:focus, QPushButton#winClose:focus {{
    border: 1px solid {t.focus};
}}

QWidget#glassPanel, QFrame#glassPanel {{
    background: {t.mantle};
    border: 1px solid {t.surface0};
    border-radius: 8px;
}}

QWidget#heroPanel, QFrame#heroPanel {{
    background: {t.mantle};
    border: 1px solid {t.surface1};
    border-radius: 8px;
}}

QLabel#sectionTitle {{
    color: {t.subtext1};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0px;
    text-transform: uppercase;
}}

QLabel#bigTitle {{
    color: {t.text};
    font-size: 22px;
    font-weight: 700;
}}

QLabel#subtitle {{
    color: {t.subtext0};
    font-size: 12px;
    line-height: 150%;
}}

QLabel#valueMuted {{
    color: {t.overlay2};
    font-size: 11px;
}}

QLabel#valueBright {{
    color: {t.text};
    font-size: 13px;
    font-weight: 600;
}}

QLabel#formLabel {{
    color: {t.subtext1};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#formValue {{
    color: {t.subtext1};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#emptyTitle {{
    color: {t.text};
    font-size: 13px;
    font-weight: 700;
}}

QLabel#emptyBody {{
    color: {t.subtext0};
    font-size: 11px;
    line-height: 150%;
}}

QWidget#emptyState {{
    background: {t.base};
    border: 1px dashed {t.surface1};
    border-radius: 8px;
}}

QLabel#statusPill {{
    background: {t.surface0};
    color: {t.subtext1};
    border: 1px solid {t.surface1};
    border-radius: 8px;
    padding: 5px 9px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#inlineNotice {{
    background: {t.base};
    color: {t.subtext0};
    border: 1px solid {t.surface0};
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 11px;
}}
QLabel#inlineNotice[tone="warning"] {{
    color: {t.yellow};
    border-color: {t.yellow};
    background: {t.yellow_soft};
}}
QLabel#inlineNotice[tone="success"] {{
    color: {t.green};
    border-color: {t.green};
    background: {t.green_soft};
}}

QPushButton#primaryBtn {{
    background: {t.accent};
    color: {t.accent_text};
    border: 1px solid {t.accent};
    border-radius: 8px;
    padding: 11px 20px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0px;
    text-transform: uppercase;
}}
QPushButton#primaryBtn:hover {{
    background: {t.accent_soft};
    border-color: {t.accent_soft};
}}
QPushButton#primaryBtn:pressed {{
    background: {t.pink};
    border-color: {t.pink};
}}
QPushButton#primaryBtn:focus {{
    border: 2px solid {t.focus};
    padding: 10px 19px;
}}
QPushButton#primaryBtn:disabled {{
    background: {t.surface1};
    border-color: {t.surface1};
    color: {t.overlay1};
}}

QPushButton#ghostBtn {{
    background: {t.base};
    color: {t.subtext1};
    border: 1px solid {t.surface1};
    border-radius: 8px;
    padding: 9px 16px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#ghostBtn:hover {{
    border-color: {t.surface2};
    color: {t.text};
    background: {t.accent_muted};
}}
QPushButton#ghostBtn:focus {{
    border: 2px solid {t.focus};
    padding: 8px 15px;
}}
QPushButton#ghostBtn:disabled {{
    background: {t.mantle};
    border-color: {t.surface0};
    color: {t.overlay0};
}}

QPushButton#modeCard {{
    background: {t.base};
    color: {t.subtext1};
    border: 1px solid {t.surface0};
    border-radius: 8px;
    padding: 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#modeCard:hover {{
    border-color: {t.accent};
    background: {t.accent_muted};
}}
QPushButton#modeCard:checked {{
    border-color: {t.accent};
    background: {t.accent_selected};
    color: {t.text};
}}
QPushButton#modeCard:disabled {{
    color: {t.overlay1};
    border-color: {t.surface0};
    background: {t.mantle};
}}
QPushButton#modeCard:focus {{
    border: 2px solid {t.focus};
}}

QPushButton#presetChip {{
    background: {t.surface0};
    color: {t.subtext1};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#presetChip:hover {{
    background: {t.surface1};
    color: {t.text};
}}
QPushButton#presetChip:checked {{
    background: {t.accent};
    color: {t.accent_text};
    border-color: {t.accent};
}}
QPushButton#presetChip:disabled {{
    background: {t.surface0};
    color: {t.overlay1};
}}
QPushButton#presetChip:focus {{
    border: 2px solid {t.focus};
    padding: 7px 11px;
}}

QLabel#dropZone {{
    color: {t.subtext0};
    border: 2px dashed {t.surface1};
    border-radius: 8px;
    padding: 28px;
    background: {t.base};
    font-size: 13px;
}}
QLabel#dropZone[hover="true"] {{
    border-color: {t.accent};
    color: {t.text};
    background: {t.accent_muted};
}}
QLabel#dropZone:focus {{
    border-color: {t.focus};
}}

QSlider::groove:horizontal {{
    height: 5px;
    background: {t.surface0};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {t.accent};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {t.text};
    border: 2px solid {t.accent};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {t.accent};
}}
QSlider:focus {{
    border: 1px solid {t.focus};
    border-radius: 8px;
}}

QProgressBar {{
    background: {t.surface0};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: {t.text};
    font-size: 11px;
    font-weight: 600;
}}
QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {t.accent},
        stop:1 {t.pink}
    );
    border-radius: 5px;
}}

QTextEdit#logPanel {{
    background: {t.crust};
    border: 1px solid {t.surface0};
    border-radius: 8px;
    color: {t.subtext0};
    font-family: "Cascadia Code", "Consolas", "Fira Code", monospace;
    font-size: 11px;
    padding: 8px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t.surface2};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.accent};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {t.surface2};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t.accent};
}}

QToolTip {{
    background: {t.surface0};
    color: {t.text};
    border: 1px solid {t.surface2};
    padding: 6px 10px;
    border-radius: 6px;
}}

QComboBox {{
    background: {t.surface0};
    border: 1px solid {t.surface1};
    border-radius: 8px;
    padding: 6px 12px;
    color: {t.text};
}}
QComboBox:hover {{
    border-color: {t.accent};
}}
QComboBox:focus {{
    border: 2px solid {t.focus};
}}
QComboBox:disabled {{
    color: {t.overlay1};
    background: {t.mantle};
    border-color: {t.surface0};
}}
QComboBox QAbstractItemView {{
    background: {t.mantle};
    color: {t.text};
    border: 1px solid {t.surface1};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
    outline: none;
}}
QComboBox#themePicker {{
    min-width: 112px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {t.crust};
    color: {t.text};
    border: 1px solid {t.surface1};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {t.focus};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background: {t.mantle};
    border-color: {t.surface0};
    color: {t.overlay1};
}}

QListView, QTreeView, QTableView {{
    background: {t.crust};
    color: {t.text};
    border: 1px solid {t.surface0};
    border-radius: 8px;
    selection-background-color: {t.accent_selected};
    selection-color: {t.text};
    alternate-background-color: {t.surface0};
}}
QListView::item, QTreeView::item, QTableView::item {{
    padding: 5px 8px;
}}
QListView::item:hover, QTreeView::item:hover, QTableView::item:hover {{
    background: {t.accent_muted};
}}
QListView::item:selected, QTreeView::item:selected, QTableView::item:selected {{
    background: {t.accent_selected};
    color: {t.text};
}}
QHeaderView::section {{
    background: {t.surface0};
    color: {t.subtext1};
    border: none;
    border-right: 1px solid {t.surface1};
    padding: 6px 8px;
    font-weight: 700;
}}

QTabWidget#sideTabs::pane {{
    border: 1px solid {t.surface0};
    border-radius: 8px;
    background: {t.mantle};
}}
QTabWidget#sideTabs QTabBar::tab {{
    background: transparent;
    color: {t.subtext0};
    padding: 9px 14px;
    border: none;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0px;
}}
QTabWidget#sideTabs QTabBar::tab:selected {{
    color: {t.text};
    border-bottom: 2px solid {t.accent};
}}
QTabWidget#sideTabs QTabBar::tab:hover {{
    color: {t.text};
}}

QSplitter::handle {{
    background: {t.base};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:hover {{
    background: {t.surface1};
}}

QMessageBox {{
    background: {t.mantle};
}}
QMessageBox QLabel {{
    color: {t.text};
}}
QDialog, QFileDialog {{
    background: {t.mantle};
    color: {t.text};
}}
QDialog QLabel, QFileDialog QLabel {{
    color: {t.text};
}}
QMessageBox QPushButton, QDialog QPushButton, QFileDialog QPushButton {{
    background: {t.base};
    color: {t.subtext1};
    border: 1px solid {t.surface1};
    border-radius: 8px;
    padding: 8px 14px;
    min-width: 78px;
    font-weight: 600;
}}
QMessageBox QPushButton:hover, QDialog QPushButton:hover, QFileDialog QPushButton:hover {{
    border-color: {t.surface2};
    color: {t.text};
    background: {t.accent_muted};
}}
QMessageBox QPushButton:focus, QDialog QPushButton:focus, QFileDialog QPushButton:focus {{
    border: 2px solid {t.focus};
}}
"""


STYLESHEET = build_stylesheet(DEFAULT_THEME_ID)
