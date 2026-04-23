# PyInstaller spec — ReelForge single-file build.
# Build:
#   pyinstaller --clean reelforge.spec
# Output:
#   dist/ReelForge.exe          (Windows)
#   dist/ReelForge / ReelForge  (macOS + Linux)

# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

project_root = Path(SPECPATH).resolve()
asset_dir = project_root / "assets"

# Platform-specific icon. On Windows we want an .ico; macOS takes .icns;
# on Linux PyInstaller ignores the icon argument for the exe but the app
# still ships the PNG alongside.
if sys.platform == "win32":
    icon_file = str(asset_dir / "icon.ico") if (asset_dir / "icon.ico").exists() else None
elif sys.platform == "darwin":
    icon_file = str(asset_dir / "icon.icns") if (asset_dir / "icon.icns").exists() else None
else:
    icon_file = None

# MediaPipe ships TFLite models inside the wheel; PyInstaller doesn't pick
# them up automatically. We copy the whole mediapipe data payload.
try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    mediapipe_datas = collect_data_files("mediapipe")
    mediapipe_hidden = collect_submodules("mediapipe")
except Exception:
    mediapipe_datas = []
    mediapipe_hidden = []

datas = [
    (str(asset_dir), "assets"),
] + mediapipe_datas

hiddenimports = [
    "PyQt6.QtMultimedia",
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
    "cv2",
    "mediapipe",
    "scenedetect",
    "scenedetect.detectors",
] + mediapipe_hidden

excludes = [
    "tkinter",
    "matplotlib",
    "scipy",
    "pandas",
    "torch",
    "tensorflow",
    "notebook",
    "IPython",
    "sphinx",
    "pytest",
    # faster-whisper is opt-in and installed at runtime on demand; keep it
    # out of the bundled exe to stay under 400 MB.
    "faster_whisper",
    "ctranslate2",
    "torchaudio",
    "onnxruntime",
]


a = Analysis(
    ["reelforge.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ReelForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX tends to break PyQt6 on Windows Defender scans
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI app — no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# On macOS, wrap the exe in a .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="ReelForge.app",
        icon=icon_file,
        bundle_identifier="com.sysadmindoc.reelforge",
        info_plist={
            "CFBundleShortVersionString": "0.4.0",
            "CFBundleVersion": "0.4.0",
            "NSHighResolutionCapable": "True",
            "LSMinimumSystemVersion": "11.0",
        },
    )
