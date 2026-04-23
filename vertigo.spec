# PyInstaller spec — Vertigo single-file build.
# Build:
#   pyinstaller --clean vertigo.spec
# Output:
#   dist/Vertigo.exe                (Windows)
#   dist/Vertigo / Vertigo.app      (Linux / macOS)

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
# them up automatically. We copy the whole data payload + every submodule.
# Same for PySceneDetect (lazy detector imports) and Pillow plugins.
try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    mediapipe_datas = collect_data_files("mediapipe")
    mediapipe_hidden = collect_submodules("mediapipe")
    scenedetect_hidden = collect_submodules("scenedetect")
    scenedetect_datas = collect_data_files("scenedetect")
    cv2_datas = collect_data_files("cv2")
    cv2_hidden = collect_submodules("cv2")
    pil_hidden = collect_submodules("PIL")
except Exception:
    mediapipe_datas = []
    mediapipe_hidden = []
    scenedetect_hidden = []
    scenedetect_datas = []
    cv2_datas = []
    cv2_hidden = []
    pil_hidden = []

datas = [
    (str(asset_dir), "assets"),
] + mediapipe_datas + scenedetect_datas + cv2_datas

hiddenimports = (
    [
        "PyQt6.QtMultimedia",
        "PyQt6.QtSvg",
        "PyQt6.QtSvgWidgets",
        # scenedetect loads detectors via string reference — force-bundle them
        "scenedetect.detectors.content_detector",
        "scenedetect.detectors.threshold_detector",
        "scenedetect.detectors.adaptive_detector",
        "scenedetect.detectors.hash_detector",
        "scenedetect.detectors.histogram_detector",
        # Pillow plugins are imported via plugin registration at PIL init
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFilter",
        "PIL.ImageFont",
        "PIL.ImageQt",
    ]
    + mediapipe_hidden
    + scenedetect_hidden
    + cv2_hidden
    + pil_hidden
)

excludes = [
    "tkinter",
    # NOTE: matplotlib + scipy are NOT excluded — MediaPipe imports them
    # internally (drawing utilities, signal processing) and skipping them
    # causes "ModuleNotFoundError: No module named 'matplotlib'" at bundle
    # import time. The ~150 MB added to the exe is the cost of correctness.
    "pandas",
    "torch",
    "tensorflow",
    "notebook",
    "IPython",
    "sphinx",
    "pytest",
    # faster-whisper is opt-in and installed at runtime on demand; keep it
    # out of the bundled exe to stay under 500 MB.
    "faster_whisper",
    "ctranslate2",
    "torchaudio",
    "onnxruntime",
]


a = Analysis(
    ["vertigo.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    # The multiprocessing runtime hook runs BEFORE user code and guarantees
    # multiprocessing.freeze_support() fires in every worker process —
    # otherwise MediaPipe / cv2 children relaunch the GUI ("fork bomb").
    runtime_hooks=[str(asset_dir / "runtime_hook_mp.py")],
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
    name="Vertigo",
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
        name="Vertigo.app",
        icon=icon_file,
        bundle_identifier="com.sysadmindoc.vertigo",
        info_plist={
            "CFBundleShortVersionString": "0.9.0",
            "CFBundleVersion": "0.9.0",
            "NSHighResolutionCapable": "True",
            "LSMinimumSystemVersion": "11.0",
        },
    )
