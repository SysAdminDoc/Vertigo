"""Validate the local Vertigo release contract before packaging.

This intentionally uses only the Python standard library so it can run before
PyInstaller is installed.  ``--build`` runs the same local PyInstaller command
documented in the README after the source/spec checks pass.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ASSETS = (
    "assets/icon.png",
    "assets/icon.svg",
    "assets/icon.ico",
    "assets/icon.icns",
    "assets/runtime_hook_mp.py",
)
REQUIRED_HIDDEN_IMPORTS = (
    "PyQt6.QtMultimedia",
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
    "numpy._core._exceptions",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFilter",
    "PIL.ImageFont",
    "PIL.ImageQt",
)


def inspect_repository(root: Path = ROOT) -> list[str]:
    """Return release-contract failures, or an empty list when clean."""

    failures: list[str] = []
    vertigo = (root / "vertigo.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    spec = (root / "vertigo.spec").read_text(encoding="utf-8")

    app_version = _match(vertigo, r"__version__\s*=\s*[\"']([^\"']+)")
    badge_version = _match(readme, r"version-([0-9]+(?:\.[0-9]+)+)-")
    bundle_versions = re.findall(
        r"CFBundle(?:ShortVersionString|Version)[\"']\s*:\s*[\"']([^\"']+)",
        spec,
    )
    if not app_version:
        failures.append("vertigo.py is missing __version__")
    if not badge_version:
        failures.append("README.md is missing the version badge")
    if not bundle_versions:
        failures.append("vertigo.spec is missing macOS bundle versions")
    versions = [value for value in (app_version, badge_version, *bundle_versions) if value]
    if versions and len(set(versions)) != 1:
        failures.append("version strings disagree: " + ", ".join(versions))

    for relative in REQUIRED_ASSETS:
        if not (root / relative).is_file():
            failures.append(f"required packaging asset is missing: {relative}")

    for hidden_import in REQUIRED_HIDDEN_IMPORTS:
        if f'"{hidden_import}"' not in spec and f"'{hidden_import}'" not in spec:
            failures.append(f"vertigo.spec is missing hidden import: {hidden_import}")
    for required_fragment in (
        "Analysis(",
        "EXE(",
        "runtime_hooks=",
        "console=False",
        "icon=icon_file",
    ):
        if required_fragment not in spec:
            failures.append(f"vertigo.spec is missing {required_fragment}")

    stale_docs = ("GitHub Actions", ".github/workflows", "gh release upload")
    for phrase in stale_docs:
        if phrase in readme:
            failures.append(f"README.md still depends on removed CI/release flow: {phrase}")

    return failures


def artifact_path(root: Path = ROOT) -> Path:
    """Return the platform's expected PyInstaller artifact path."""

    if os.name == "nt":
        return root / "dist" / "Vertigo.exe"
    if sys.platform == "darwin":
        return root / "dist" / "Vertigo.app"
    return root / "dist" / "Vertigo"


def _match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        action="store_true",
        help="run the local PyInstaller build after the source checks",
    )
    parser.add_argument(
        "--artifact",
        action="store_true",
        help="also require the expected artifact under dist/",
    )
    args = parser.parse_args(argv)

    failures = inspect_repository()
    if args.artifact and not artifact_path().exists():
        failures.append(f"packaging artifact is missing: {artifact_path()}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    version = _match(
        (ROOT / "vertigo.py").read_text(encoding="utf-8"),
        r"__version__\s*=\s*[\"']([^\"']+)",
    )
    print(f"release sanity OK: Vertigo {version}")
    print(f"assets OK: {len(REQUIRED_ASSETS)} required files")
    print(f"hidden imports OK: {len(REQUIRED_HIDDEN_IMPORTS)} required entries")

    if not args.build:
        return 0
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "vertigo.spec",
    ]
    print("running:", " ".join(command))
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        return result.returncode
    if not artifact_path().exists():
        print(f"FAIL: PyInstaller returned success but artifact is missing: {artifact_path()}")
        return 1
    print(f"artifact OK: {artifact_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
