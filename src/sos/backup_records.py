"""Backup record management: metadata I/O, listing, finding, and validation.

Extracted from backups.py to separate the record-management concern (reading
and writing metadata.toml, listing backups, validating metadata fields) from
backup creation and restore execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sos.models import BackupRecord
from sos.paths import RuntimePaths
from sos.path_safety import safe_component
from sos.toml_io import read_toml, write_toml


METADATA_FILE = "metadata.toml"
CONFIG_SNAPSHOT = "config.toml"
VAULT_SNAPSHOT = "vault"
WORKSPACE_AGENTS_SNAPSHOT = "workspace-agents"
LEARNED_REFERENCE_SNAPSHOT = "learned-reference.md"
WORKSPACE_ACTIVATION_SCOPE = "workspace_activation"


# ---------------------------------------------------------------------------
# Public record-management API
# ---------------------------------------------------------------------------

def list_backups(runtime_paths: RuntimePaths) -> tuple[BackupRecord, ...]:
    if not runtime_paths.backups.is_dir():
        return ()

    records = tuple(
        _read_backup_record(metadata_path)
        for metadata_path in runtime_paths.backups.glob(f"*/{METADATA_FILE}")
    )
    return tuple(
        sorted(
            records,
            key=lambda record: (record.created_at, record.backup_id),
            reverse=True,
        )
    )


def annotate_backup_metadata(
    runtime_paths: RuntimePaths,
    backup_id: str,
    codex_config_path: Path,
    active_skill_root: Path,
    host: str,
) -> None:
    """Augment a backup's metadata with vault/config/root context after a successful apply."""
    metadata_path = runtime_paths.backups / backup_id / METADATA_FILE
    if not metadata_path.exists():
        return
    metadata = read_toml(metadata_path)
    next_metadata: dict[str, Any] = {
        **metadata,
        "vault_root": _metadata_path_value(runtime_paths.vault),
        "active_skill_root": _metadata_path_value(active_skill_root),
        "host": host,
    }
    if host == "codex":
        next_metadata["codex_config_path"] = _metadata_path_value(codex_config_path)
    write_toml(metadata_path, next_metadata)


def restore_targets(
    runtime_paths: RuntimePaths,
    backup_id: str,
) -> tuple[Path | None, Path | None]:
    """Resolve (codex_config_path, vault_root) restore targets from a backup's metadata."""
    safe_component(backup_id, "backup_id")
    metadata_path = runtime_paths.backups / backup_id / METADATA_FILE
    metadata = read_toml(metadata_path)
    if metadata.get("scope") == WORKSPACE_ACTIVATION_SCOPE:
        return None, None
    if "vault_root" not in metadata:
        raise ValueError("backup restore metadata must include vault_root")
    host = str(metadata.get("host", "codex"))
    vault_root = Path(str(metadata["vault_root"]))
    if host == "codex":
        if "codex_config_path" not in metadata:
            raise ValueError("codex backup restore metadata must include codex_config_path")
        codex_config_path = Path(str(metadata["codex_config_path"]))
        return codex_config_path, vault_root
    # claude: no codex_config_path
    return None, vault_root


# ---------------------------------------------------------------------------
# Shared helpers (used by creation, restore, and record management)
# ---------------------------------------------------------------------------

def metadata_path_value(path: Path) -> str:
    return path.expanduser().resolve(strict=False).as_posix()


# Alias for backward compatibility within the package.
_metadata_path_value = metadata_path_value


def snapshot_optional_path(path: Path, snapshot_path: Path) -> tuple[str, Path | None]:
    if path.is_dir():
        import shutil

        shutil.copytree(path, snapshot_path)
        return "dir", snapshot_path
    if path.exists():
        import shutil

        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, snapshot_path)
        return "file", snapshot_path
    return "missing", None


# Alias for backward compatibility within the package.
_snapshot_optional_path = snapshot_optional_path


def require_absolute_metadata_path(raw_value: Any, label: str) -> None:
    """Reject raw metadata path values that are not absolute.

    This guards against old-format backups that stored relative paths:
    ``resolve()`` would silently resolve them against the current cwd,
    which may differ from the original cwd at backup time.
    """
    path = Path(str(raw_value))
    if not path.is_absolute():
        raise ValueError(
            f"backup metadata {label} must be absolute, got: {raw_value!r}"
        )


_require_absolute_metadata_path = require_absolute_metadata_path


def reserve_backup_id(backups_root: Path, created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
    base_backup_id = f"backup-{timestamp}"
    backup_id = base_backup_id
    counter = 2
    while (backups_root / backup_id).exists():
        backup_id = f"{base_backup_id}-{counter}"
        counter += 1
    return backup_id


_reserve_backup_id = reserve_backup_id


def backup_metadata(
    backup_id: str,
    created_at: datetime,
    reason: str,
    config_snapshot_path: Path | None,
    vault_snapshot_path: Path | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "backup_id": backup_id,
        "created_at": created_at.isoformat(),
        "reason": reason,
    }
    if config_snapshot_path is not None:
        metadata["config_snapshot_path"] = config_snapshot_path.as_posix()
    if vault_snapshot_path is not None:
        metadata["vault_snapshot_path"] = vault_snapshot_path.as_posix()
    return metadata


_backup_metadata = backup_metadata


def read_backup_record(metadata_path: Path) -> BackupRecord:
    metadata = read_toml(metadata_path)
    backup_id = str(metadata["backup_id"])
    _validate_metadata_backup_id(backup_id, metadata_path)
    return BackupRecord(
        backup_id=backup_id,
        created_at=_parse_created_at(metadata["created_at"]),
        config_path=_optional_path(metadata.get("config_snapshot_path")),
        vault_path=_optional_path(metadata.get("vault_snapshot_path")),
        metadata=metadata,
    )


_read_backup_record = read_backup_record


def find_backup(runtime_paths: RuntimePaths, backup_id: str) -> BackupRecord:
    _validate_backup_id_component(backup_id)
    metadata_path = runtime_paths.backups / backup_id / METADATA_FILE
    if not metadata_path.is_file():
        raise ValueError(f"Backup not found: {backup_id}")
    return _read_backup_record(metadata_path)


_find_backup = find_backup


def validate_backup_id_component(backup_id: str) -> None:
    safe_component(backup_id, "backup_id")


_validate_backup_id_component = validate_backup_id_component


def validate_metadata_active_skill_root(record: BackupRecord) -> Path:
    value = record.metadata.get("active_skill_root")
    if not isinstance(value, str) or not value:
        raise ValueError("metadata missing active_skill_root; cannot validate restore paths")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"active_skill_root must be absolute: {value!r}")
    return path.resolve(strict=False)


_validate_metadata_active_skill_root = validate_metadata_active_skill_root


def safe_metadata_component(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"archive restore entry {label} must be a string")
    try:
        return safe_component(value, label)
    except ValueError as error:
        raise ValueError(f"unsafe archive restore entry {label}: {value}") from error


_safe_metadata_component = safe_metadata_component


def required_metadata_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"archive restore entry {label} must be a path string")
    return Path(value)


_required_metadata_path = required_metadata_path


def optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


_optional_path = optional_path


def validate_snapshot_under_backup(
    snapshot_path: Path,
    backup_id: str,
    backups_root: Path,
) -> None:
    """Assert that *snapshot_path* is contained within the backup directory."""
    resolved_snapshot = snapshot_path.resolve(strict=False)
    backup_dir = (backups_root / backup_id).resolve(strict=False)
    if resolved_snapshot != backup_dir and not resolved_snapshot.is_relative_to(backup_dir):
        raise ValueError(
            f"snapshot path escapes backup directory: {snapshot_path}"
        )


_validate_snapshot_under_backup = validate_snapshot_under_backup


def validate_snapshot_kind(kind: str, snapshot_path: Path | None, label: str) -> None:
    if kind == "missing":
        if snapshot_path is not None:
            raise ValueError(f"snapshot kind mismatch for {label}: missing has snapshot")
        return
    if snapshot_path is None:
        raise ValueError(f"snapshot kind mismatch for {label}: snapshot path missing")
    if kind == "dir":
        if not snapshot_path.is_dir():
            raise ValueError(f"snapshot kind mismatch for {label}: expected directory")
        return
    if kind == "file":
        if not snapshot_path.is_file():
            raise ValueError(f"snapshot kind mismatch for {label}: expected file")
        return
    raise ValueError(f"unknown snapshot kind for {label}: {kind}")


_validate_snapshot_kind = validate_snapshot_kind


def _validate_metadata_backup_id(backup_id: str, metadata_path: Path) -> None:
    safe_backup_id = safe_component(backup_id, "backup_id")
    backup_dir_name = metadata_path.parent.name
    if safe_backup_id != backup_dir_name:
        raise ValueError(
            f"Backup metadata backup_id must be one safe path component matching {backup_dir_name!r}: "
            f"{backup_id!r}"
        )


def _parse_created_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        created_at = value
    else:
        created_at = datetime.fromisoformat(str(value))
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC)
