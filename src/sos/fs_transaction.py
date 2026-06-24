"""Shared filesystem transaction primitives.

Provides snapshot, rollback, and atomic-replace helpers used by every write-path
module (apply, sync, workspace_activation).  Extracted from three near-identical
private copies to guarantee consistent rollback behaviour and a single test surface.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathSnapshot:
    """A captured state of a filesystem path for later rollback."""

    path: Path
    kind: str  # "dir", "file", or "missing"
    backup_path: Path | None = None


def snapshot_paths(
    paths: tuple[Path, ...],
    *,
    prefix: str = "sos-rollback-",
) -> tuple[tuple[PathSnapshot, ...], Path]:
    """Snapshot the given paths into a temp dir.

    Returns ``(snapshots, snapshot_root)``.  The caller is responsible for
    cleaning up ``snapshot_root`` (typically in a ``finally`` block).
    """
    snapshot_root = Path(tempfile.mkdtemp(prefix=prefix))
    snapshots = tuple(
        _snapshot_path(path, snapshot_root, index)
        for index, path in enumerate(unique_paths(paths))
    )
    return snapshots, snapshot_root


def restore_snapshots(snapshots: tuple[PathSnapshot, ...]) -> None:
    """Restore snapshots in reverse order (last captured, first restored)."""
    for snapshot in reversed(snapshots):
        _restore_snapshot(snapshot)


def remove_path(path: Path) -> None:
    """Remove a file or directory at *path*.  No-op if the path does not exist."""
    if path.is_dir():
        shutil.rmtree(path)
        return
    if path.exists():
        path.unlink()


def unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """Deduplicate paths by resolved string form, preserving first-seen order."""
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def _snapshot_path(path: Path, snapshot_root: Path, index: int) -> PathSnapshot:
    backup_path = snapshot_root / str(index)
    if path.is_dir():
        shutil.copytree(path, backup_path)
        return PathSnapshot(path=path, kind="dir", backup_path=backup_path)
    if path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        return PathSnapshot(path=path, kind="file", backup_path=backup_path)
    return PathSnapshot(path=path, kind="missing")


def _restore_snapshot(snapshot: PathSnapshot) -> None:
    if snapshot.kind == "missing":
        remove_path(snapshot.path)
        return
    if snapshot.backup_path is None:
        raise ValueError(f"snapshot backup path missing for {snapshot.path}")

    remove_path(snapshot.path)
    snapshot.path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.kind == "dir":
        shutil.copytree(snapshot.backup_path, snapshot.path)
        return
    if snapshot.kind == "file":
        shutil.copy2(snapshot.backup_path, snapshot.path)
        return
    raise ValueError(f"unknown snapshot kind: {snapshot.kind}")
