from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sos.models import BackupRecord
from sos.paths import RuntimePaths
from sos.toml_io import read_toml, write_toml


METADATA_FILE = "metadata.toml"
CONFIG_SNAPSHOT = "config.toml"
VAULT_SNAPSHOT = "vault"


def create_backup(
    runtime_paths: RuntimePaths,
    codex_config_path: str | Path | None,
    vault_root: str | Path | None,
    reason: str,
) -> BackupRecord:
    runtime_paths.backups.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    backup_id = _reserve_backup_id(runtime_paths.backups, created_at)
    backup_dir = runtime_paths.backups / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)

    config_snapshot_path: Path | None = None
    if codex_config_path is not None:
        config_source = Path(codex_config_path)
        if config_source.is_file():
            config_snapshot_path = backup_dir / CONFIG_SNAPSHOT
            shutil.copy2(config_source, config_snapshot_path)

    vault_snapshot_path: Path | None = None
    if vault_root is not None:
        vault_source = Path(vault_root)
        if vault_source.is_dir():
            vault_snapshot_path = backup_dir / VAULT_SNAPSHOT
            shutil.copytree(vault_source, vault_snapshot_path)

    metadata = _backup_metadata(
        backup_id=backup_id,
        created_at=created_at,
        reason=reason,
        config_snapshot_path=config_snapshot_path,
        vault_snapshot_path=vault_snapshot_path,
    )
    write_toml(backup_dir / METADATA_FILE, metadata)

    return BackupRecord(
        backup_id=backup_id,
        created_at=created_at,
        config_path=config_snapshot_path,
        vault_path=vault_snapshot_path,
        metadata=metadata,
    )


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


def restore_backup(
    runtime_paths: RuntimePaths,
    backup_id: str,
    codex_config_path: str | Path,
    vault_root: str | Path,
    apply: bool,
) -> BackupRecord:
    record = _find_backup(runtime_paths, backup_id)
    if not apply:
        return record

    config_target = Path(codex_config_path)
    config_rollback_path: Path | None = None
    config_target_existed = config_target.exists()
    config_replaced = False

    try:
        if record.config_path is not None:
            if config_target_existed:
                config_rollback_path = _reserved_sibling_temp_path(config_target, suffix=".rollback")
                shutil.copy2(config_target, config_rollback_path)
            _replace_file_atomic(record.config_path, config_target)
            config_replaced = True
        if record.vault_path is not None:
            _replace_directory_atomic(record.vault_path, Path(vault_root))
    except Exception:
        if config_replaced:
            _restore_config_rollback(config_rollback_path, config_target, config_target_existed)
            config_rollback_path = None
        raise
    finally:
        if config_rollback_path is not None and config_rollback_path.exists():
            config_rollback_path.unlink()

    return record


def prune_backups(
    runtime_paths: RuntimePaths,
    keep: int,
    apply: bool,
) -> tuple[BackupRecord, ...]:
    if keep < 0:
        raise ValueError("keep must be non-negative")

    records = list_backups(runtime_paths)
    kept = records[:keep]

    if apply:
        for record in records[keep:]:
            shutil.rmtree(runtime_paths.backups / record.backup_id)

    return kept


def _reserve_backup_id(backups_root: Path, created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
    base_backup_id = f"backup-{timestamp}"
    backup_id = base_backup_id
    counter = 2
    while (backups_root / backup_id).exists():
        backup_id = f"{base_backup_id}-{counter}"
        counter += 1
    return backup_id


def _backup_metadata(
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
        metadata["config_snapshot_path"] = str(config_snapshot_path)
    if vault_snapshot_path is not None:
        metadata["vault_snapshot_path"] = str(vault_snapshot_path)
    return metadata


def _read_backup_record(metadata_path: Path) -> BackupRecord:
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


def _validate_metadata_backup_id(backup_id: str, metadata_path: Path) -> None:
    backup_dir_name = metadata_path.parent.name
    if (
        not backup_id
        or backup_id in {".", ".."}
        or Path(backup_id).is_absolute()
        or "/" in backup_id
        or "\\" in backup_id
        or backup_id != backup_dir_name
    ):
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


def _optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


def _find_backup(runtime_paths: RuntimePaths, backup_id: str) -> BackupRecord:
    _validate_backup_id_component(backup_id)
    metadata_path = runtime_paths.backups / backup_id / METADATA_FILE
    if not metadata_path.is_file():
        raise ValueError(f"Backup not found: {backup_id}")
    return _read_backup_record(metadata_path)


def _validate_backup_id_component(backup_id: str) -> None:
    if (
        not backup_id
        or backup_id in {".", ".."}
        or Path(backup_id).is_absolute()
        or "/" in backup_id
        or "\\" in backup_id
        or Path(backup_id).name != backup_id
    ):
        raise ValueError(f"unsafe backup_id: {backup_id}")


def _replace_file_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _reserved_sibling_temp_path(target, suffix=".tmp")
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _restore_config_rollback(
    rollback_path: Path | None,
    target: Path,
    target_existed: bool,
) -> None:
    if target_existed:
        if rollback_path is None:
            return
        os.replace(rollback_path, target)
        return
    if target.exists():
        target.unlink()


def _replace_directory_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _reserved_sibling_temp_path(target, suffix=".tmp")
    backup_path: Path | None = None

    try:
        shutil.copytree(source, temp_path)
        if target.exists():
            backup_path = _reserved_sibling_temp_path(target, suffix=".bak")
            os.replace(target, backup_path)
        os.replace(temp_path, target)
        if backup_path is not None:
            shutil.rmtree(backup_path)
            backup_path = None
    except Exception:
        if backup_path is not None and backup_path.exists() and not target.exists():
            os.replace(backup_path, target)
            backup_path = None
        raise
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)
        if backup_path is not None and backup_path.exists() and target.exists():
            shutil.rmtree(backup_path)


def _reserved_sibling_temp_path(target_path: Path, suffix: str) -> Path:
    temp_path = Path(
        tempfile.mkdtemp(
            prefix=f".{target_path.name}.",
            suffix=suffix,
            dir=target_path.parent,
        )
    )
    temp_path.rmdir()
    return temp_path
