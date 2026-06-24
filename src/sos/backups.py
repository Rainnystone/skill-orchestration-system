"""Backup creation and public facade.

Backup creation logic lives here.  Record management (metadata I/O, listing,
finding, validation) lives in backup_records.py, and restore execution lives
in backup_restore.py.  This module re-exports the public API so that
``from sos.backups import ...`` continues to work for all callers.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from sos.backup_records import (
    CONFIG_SNAPSHOT,
    LEARNED_REFERENCE_SNAPSHOT,
    METADATA_FILE,
    VAULT_SNAPSHOT,
    WORKSPACE_ACTIVATION_SCOPE,
    WORKSPACE_AGENTS_SNAPSHOT,
    annotate_backup_metadata,
    list_backups,
    metadata_path_value,
    reserve_backup_id,
    backup_metadata,
    restore_targets,
    snapshot_optional_path,
    validate_backup_id_component,
)
from sos.backup_restore import (
    prune_backups,
    restore_backup,
    _replace_directory_atomic,
)
from sos.host_paths import validate_host, workspace_skill_parent_for_host, workspace_skill_root_for_host
from sos.models import BackupRecord, PackManifest
from sos.paths import RuntimePaths
from sos.toml_io import read_toml, write_toml

# Backward-compatible aliases for code that referenced the private names.
_metadata_path_value = metadata_path_value
_reserve_backup_id = reserve_backup_id
_backup_metadata = backup_metadata
_snapshot_optional_path = snapshot_optional_path
_validate_backup_id_component = validate_backup_id_component


def create_backup(
    runtime_paths: RuntimePaths,
    codex_config_path: str | Path | None,
    vault_root: str | Path | None,
    reason: str,
) -> BackupRecord:
    runtime_paths.backups.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    backup_id = reserve_backup_id(runtime_paths.backups, created_at)
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

    metadata = backup_metadata(
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


def record_claude_archive_restore_entries(
    runtime_paths: RuntimePaths,
    backup_id: str,
    manifests: tuple[PackManifest, ...],
) -> None:
    metadata_path = runtime_paths.backups / backup_id / METADATA_FILE
    if not metadata_path.exists():
        return
    metadata = read_toml(metadata_path)
    metadata["archive_restore_entries"] = _archive_restore_entries_from_manifests(
        manifests
    )
    write_toml(metadata_path, metadata)


def _archive_restore_entries_from_manifests(
    manifests: tuple[PackManifest, ...],
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for manifest in manifests:
        if manifest.host != "claude":
            continue
        for skill in manifest.skills:
            if skill.archived_source_path is None:
                continue
            entries.append(
                {
                    "pack_id": manifest.id,
                    "skill_name": skill.name,
                    "archive_path": metadata_path_value(skill.archived_source_path),
                    "source_path": metadata_path_value(skill.source_path),
                }
            )
    return entries


def create_workspace_activation_backup(
    runtime_paths: RuntimePaths,
    workspace_root: str | Path,
    workspace_skill_parent_root: str | Path,
    learned_reference_target: str | Path,
    reason: str,
    *,
    host: str = "codex",
) -> BackupRecord:
    safe_host = validate_host(host)
    workspace_root_path = Path(workspace_root)
    skill_parent_target = Path(workspace_skill_parent_root)
    learned_target = Path(learned_reference_target)
    expected_skill_parent = workspace_skill_parent_for_host(workspace_root_path, safe_host)
    if skill_parent_target.resolve(strict=False) != expected_skill_parent.resolve(strict=False):
        raise ValueError("workspace activation backup skill parent target mismatch")

    runtime_paths.backups.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    backup_id = reserve_backup_id(runtime_paths.backups, created_at)
    backup_dir = runtime_paths.backups / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)
    skill_parent_kind, skill_parent_snapshot = snapshot_optional_path(
        skill_parent_target,
        backup_dir / WORKSPACE_AGENTS_SNAPSHOT,
    )
    learned_kind, learned_snapshot = snapshot_optional_path(
        learned_target,
        backup_dir / LEARNED_REFERENCE_SNAPSHOT,
    )
    metadata = {
        "backup_id": backup_id,
        "created_at": created_at.isoformat(),
        "reason": reason,
        "scope": WORKSPACE_ACTIVATION_SCOPE,
        "host": safe_host,
        "workspace_root": metadata_path_value(workspace_root_path),
        "workspace_skill_parent_target": metadata_path_value(skill_parent_target),
        "workspace_skill_parent_kind": skill_parent_kind,
        "workspace_skill_root": metadata_path_value(workspace_skill_root_for_host(workspace_root_path, safe_host)),
        "learned_reference_target": metadata_path_value(learned_target),
        "learned_reference_kind": learned_kind,
    }
    if skill_parent_snapshot is not None:
        metadata["workspace_skill_parent_snapshot_path"] = metadata_path_value(
            skill_parent_snapshot
        )
    if learned_snapshot is not None:
        metadata["learned_reference_snapshot_path"] = metadata_path_value(learned_snapshot)
    write_toml(backup_dir / METADATA_FILE, metadata)

    return BackupRecord(
        backup_id=backup_id,
        created_at=created_at,
        metadata=metadata,
    )


__all__ = [
    "CONFIG_SNAPSHOT",
    "LEARNED_REFERENCE_SNAPSHOT",
    "METADATA_FILE",
    "VAULT_SNAPSHOT",
    "WORKSPACE_ACTIVATION_SCOPE",
    "WORKSPACE_AGENTS_SNAPSHOT",
    "annotate_backup_metadata",
    "create_backup",
    "create_workspace_activation_backup",
    "list_backups",
    "prune_backups",
    "record_claude_archive_restore_entries",
    "restore_backup",
    "restore_targets",
]
