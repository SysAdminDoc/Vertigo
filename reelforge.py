#!/usr/bin/env python3
"""ReelForge v0.4.0 — premium vertical-video forge for Shorts / TikTok / Reels.

Turnkey entry: bootstraps dependencies on first run, then launches the GUI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

__version__ = "0.4.0"
APP_NAME = "ReelForge"

_REQUIRED = [
    ("PyQt6",        "PyQt6>=6.7.0"),
    ("cv2",          "opencv-python>=4.10.0"),
    ("numpy",        "numpy>=1.26.0"),
    ("PIL",          "Pillow>=10.3.0"),
    ("mediapipe",    "mediapipe>=0.10.14"),
    ("scenedetect",  "scenedetect>=0.6.5"),
]


# ---------------------------------------------------------------- bootstrap

def _pip_install(spec: str) -> bool:
    """Try three install strategies. Return True on success."""
    bases = [
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", spec],
        [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check", spec],
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "--disable-pip-version-check", spec],
    ]
    for cmd in bases:
        try:
            rc = subprocess.call(cmd)
            if rc == 0:
                return True
        except Exception:
            continue
    return False


def _bootstrap() -> None:
    """Import each required module; pip-install any that's missing."""
    missing: list[str] = []
    for mod, spec in _REQUIRED:
        try:
            __import__(mod)
        except ImportError:
            missing.append(spec)

    if missing:
        print(f"[{APP_NAME}] bootstrapping: {', '.join(missing)}")
        for spec in missing:
            ok = _pip_install(spec)
            if not ok:
                sys.stderr.write(f"[{APP_NAME}] failed to install {spec}\n")
                sys.exit(2)
        print(f"[{APP_NAME}] bootstrap complete.")


def _check_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.stderr.write(
            f"[{APP_NAME}] FFmpeg / ffprobe not found on PATH.\n"
            f"  Install FFmpeg and relaunch. On Windows:\n"
            f"    winget install Gyan.FFmpeg\n"
        )
        sys.exit(3)


# ---------------------------------------------------------------- main

def main() -> int:
    _bootstrap()
    _check_ffmpeg()

    # late imports so bootstrap can install them first
    sys.path.insert(0, str(Path(__file__).parent))
    from PyQt6.QtCore import Qt, QSettings
    from PyQt6.QtGui import QFont, QIcon
    from PyQt6.QtWidgets import QApplication

    from ui.assets import icon_path
    from ui.main_window import MainWindow
    from ui.theme import apply_app_theme, sanitize_theme_preference

    if sys.platform == "win32":
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    icon = QIcon(str(icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)

    theme_pref = sanitize_theme_preference(
        QSettings("ReelForge", "ReelForge").value("theme", "system", type=str)
    )
    apply_app_theme(app, theme_pref)

    win = MainWindow()
    if not icon.isNull():
        win.setWindowIcon(icon)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
