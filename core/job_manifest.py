"""Atomic, local state for resumable batch exports.

The manifest is deliberately JSON and human-readable. It stores the batch
recipe and per-source output state, but never secrets or media bytes. A
``.part`` output is the only file the cleanup helper removes automatically.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import crashlog


SCHEMA_VERSION = 1
IN_PROGRESS_STATES = frozenset({"running", "interrupted"})
DONE_ENTRY_STATUS = "done"


def manifest_path() -> Path:
    """Return the user-local manifest path, with a test/operator override."""
    override = os.environ.get("VERTIGO_BATCH_MANIFEST")
    if override:
        return Path(override)
    return crashlog.crash_log_path().with_name("batch-manifest.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ManifestEntry:
    source_path: Path
    output_path: Path | None = None
    temp_output_path: Path | None = None
    status: str = "pending"
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "output_path": str(self.output_path) if self.output_path else None,
            "temp_output_path": str(self.temp_output_path) if self.temp_output_path else None,
            "status": self.status,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ManifestEntry":
        if not isinstance(raw, dict):
            raise ValueError("manifest entry must be an object")
        source = raw.get("source_path")
        if not source:
            raise ValueError("manifest entry is missing source_path")
        return cls(
            source_path=Path(str(source)),
            output_path=_path_or_none(raw.get("output_path")),
            temp_output_path=_path_or_none(raw.get("temp_output_path")),
            status=str(raw.get("status") or "pending"),
            message=str(raw.get("message") or ""),
        )


@dataclass
class BatchManifest:
    """The recipe and progress ledger for one batch run."""

    batch_id: str
    output_dir: Path
    preset_id: str
    mode: str
    trim_low: float
    trim_high: float
    options: dict[str, Any] = field(default_factory=dict)
    entries: list[ManifestEntry] = field(default_factory=list)
    state: str = "running"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def new(
        cls,
        *,
        output_dir: Path,
        preset_id: str,
        mode: str,
        trim_low: float,
        trim_high: float,
        options: dict[str, Any],
        entries: list[ManifestEntry],
    ) -> "BatchManifest":
        return cls(
            batch_id=uuid.uuid4().hex[:12],
            output_dir=Path(output_dir),
            preset_id=preset_id,
            mode=mode,
            trim_low=float(trim_low),
            trim_high=float(trim_high),
            options=dict(options),
            entries=list(entries),
        )

    @property
    def incomplete(self) -> bool:
        return self.state in IN_PROGRESS_STATES

    @property
    def pending_entries(self) -> list[ManifestEntry]:
        return [entry for entry in self.entries if entry.status != DONE_ENTRY_STATUS]

    def find(self, source_path: Path) -> ManifestEntry | None:
        source = Path(source_path)
        return next(
            (entry for entry in self.entries if entry.source_path == source),
            None,
        )

    def touch(self) -> None:
        self.updated_at = _now()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "batch_id": self.batch_id,
            "output_dir": str(self.output_dir),
            "preset_id": self.preset_id,
            "mode": self.mode,
            "trim": {"low": self.trim_low, "high": self.trim_high},
            "options": self.options,
            "entries": [entry.as_dict() for entry in self.entries],
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BatchManifest":
        if not isinstance(raw, dict):
            raise ValueError("manifest root must be an object")
        if int(raw.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("unsupported batch manifest schema")
        trim = raw.get("trim") or {}
        entries = raw.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("manifest has no entries")
        return cls(
            batch_id=str(raw.get("batch_id") or "legacy"),
            output_dir=Path(str(raw.get("output_dir") or ".")),
            preset_id=str(raw.get("preset_id") or "shorts"),
            mode=str(raw.get("mode") or "center"),
            trim_low=float(trim.get("low", 0.0)),
            trim_high=float(trim.get("high", 0.0)),
            options=dict(raw.get("options") or {}),
            entries=[ManifestEntry.from_dict(item) for item in entries],
            state=str(raw.get("state") or "interrupted"),
            created_at=str(raw.get("created_at") or _now()),
            updated_at=str(raw.get("updated_at") or _now()),
        )


def save(manifest: BatchManifest, path: Path | None = None) -> Path:
    """Atomically publish a manifest beside the crash log."""
    target = Path(path) if path is not None else manifest_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n"
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def load(path: Path | None = None) -> BatchManifest | None:
    """Load a valid manifest, logging and ignoring corrupt local state."""
    target = Path(path) if path is not None else manifest_path()
    if not target.exists():
        return None
    try:
        with target.open("r", encoding="utf-8") as handle:
            return BatchManifest.from_dict(json.load(handle))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        crashlog.append(f"batch manifest ignored: {type(exc).__name__}: {exc}")
        return None


def discard(path: Path | None = None) -> None:
    """Remove only the manifest file itself."""
    target = Path(path) if path is not None else manifest_path()
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        crashlog.append(f"batch manifest could not be discarded: {exc}")


def cleanup_partial_outputs(manifest: BatchManifest) -> list[Path]:
    """Remove recorded hidden ``.part`` files inside the output directory."""
    root = manifest.output_dir.expanduser().resolve(strict=False)
    removed: list[Path] = []
    candidates = [
        entry.temp_output_path
        for entry in manifest.entries
        if entry.temp_output_path is not None
    ]
    if root.is_dir():
        candidates.extend(
            child
            for child in root.iterdir()
            if child.name.startswith(f".vertigo-{manifest.batch_id}-")
        )
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate is None or not candidate.name.startswith(".vertigo-"):
            continue
        resolved = candidate.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if not _is_within(resolved, root):
            continue
        try:
            resolved.unlink(missing_ok=True)
            removed.append(resolved)
        except OSError as exc:
            crashlog.append(f"batch partial output could not be removed: {exc}")
    return removed


def _path_or_none(raw: Any) -> Path | None:
    return Path(str(raw)) if raw else None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return path != root
    except ValueError:
        return False
