from __future__ import annotations

import os
import shutil
import tempfile
from sos.path_safety import cross_platform_path_key, safe_component
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sos.models import BackupRecord, PackManifest
from sos.paths import RuntimePaths
from sos.toml_io import read_toml, write_toml


METADATA_FILE = "metadata.toml"
CONFIG_SNAPSHOT = "config.toml"
VAULT_SNAPSHOT = "vault"
WORKSPACE_AGENTS_SNAPSHOT = "workspace-agents"
LEARNED_REFERENCE_SNAPSHOT = "learned-reference.md"
WORKSPACE_ACTIVATION_SCOPE = "workspace_activation"


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


def record_claude_archive_restore_entries(
    runtime_paths: RuntimePaths,
    backup_id: str,
    manifests: tuple[PackManifest, ...],
) -> None:
    metadata_path = runtime_paths.backups / backup_id / "metadata.toml"
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
                    "archive_path": skill.archived_source_path.as_posix(),
                    "source_path": skill.source_path.as_posix(),
                }
            )
    return entries


def create_workspace_activation_backup(
    runtime_paths: RuntimePaths,
    workspace_root: str | Path,
    workspace_agents_root: str | Path,
    learned_reference_target: str | Path,
    reason: str,
) -> BackupRecord:
    runtime_paths.backups.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    backup_id = _reserve_backup_id(runtime_paths.backups, created_at)
    backup_dir = runtime_paths.backups / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)

    workspace_root_path = Path(workspace_root)
    agents_target = Path(workspace_agents_root)
    learned_target = Path(learned_reference_target)
    agents_kind, agents_snapshot = _snapshot_optional_path(
        agents_target,
        backup_dir / WORKSPACE_AGENTS_SNAPSHOT,
    )
    learned_kind, learned_snapshot = _snapshot_optional_path(
        learned_target,
        backup_dir / LEARNED_REFERENCE_SNAPSHOT,
    )
    metadata = {
        "backup_id": backup_id,
        "created_at": created_at.isoformat(),
        "reason": reason,
        "scope": WORKSPACE_ACTIVATION_SCOPE,
        "workspace_root": str(workspace_root_path),
        "workspace_agents_target": str(agents_target),
        "workspace_agents_kind": agents_kind,
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": learned_kind,
    }
    if agents_snapshot is not None:
        metadata["workspace_agents_snapshot_path"] = agents_snapshot.as_posix()
    if learned_snapshot is not None:
        metadata["learned_reference_snapshot_path"] = learned_snapshot.as_posix()
    write_toml(backup_dir / METADATA_FILE, metadata)

    return BackupRecord(
        backup_id=backup_id,
        created_at=created_at,
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
    codex_config_path: str | Path | None,
    vault_root: str | Path | None,
    apply: bool,
) -> BackupRecord:
    record = _find_backup(runtime_paths, backup_id)
    if not apply:
        return record

    if record.metadata.get("scope") == WORKSPACE_ACTIVATION_SCOPE:
        _restore_workspace_activation_backup(runtime_paths, record)
        return record

    host = str(record.metadata.get("host", "codex"))

    if host == "claude":
        archive_moves = _planned_archive_restore_for_backup(record, runtime_paths)
        archive_restored = False
        try:
            _restore_archive_moves(archive_moves)
            archive_restored = True
            if record.vault_path is not None:
                if vault_root is None:
                    raise ValueError("vault_root is required for vault restore")
                _replace_directory_atomic(record.vault_path, Path(vault_root))
        except Exception:
            if archive_restored:
                _rollback_restored_archive_moves(archive_moves)
            raise
        return record

    config_target = Path(codex_config_path) if codex_config_path is not None else None
    config_rollback_path: Path | None = None
    config_target_existed = config_target.exists() if config_target is not None else False
    config_replaced = False

    try:
        if record.config_path is not None and config_target is not None:
            if config_target_existed:
                config_rollback_path = _reserved_sibling_temp_path(config_target, suffix=".rollback")
                shutil.copy2(config_target, config_rollback_path)
            _replace_file_atomic(record.config_path, config_target)
            config_replaced = True
        if record.vault_path is not None:
            if vault_root is None:
                raise ValueError("vault_root is required for vault restore")
            _replace_directory_atomic(record.vault_path, Path(vault_root))
    except Exception:
        if config_replaced and config_target is not None:
            _restore_config_rollback(config_rollback_path, config_target, config_target_existed)
            config_rollback_path = None
        raise
    finally:
        if config_rollback_path is not None and config_rollback_path.exists():
            config_rollback_path.unlink()

    return record


def _snapshot_optional_path(path: Path, snapshot_path: Path) -> tuple[str, Path | None]:
    if path.is_dir():
        shutil.copytree(path, snapshot_path)
        return "dir", snapshot_path
    if path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, snapshot_path)
        return "file", snapshot_path
    return "missing", None


def _restore_workspace_activation_backup(
    runtime_paths: RuntimePaths,
    record: BackupRecord,
) -> None:
    metadata = record.metadata
    workspace_root = Path(str(metadata["workspace_root"]))
    agents_target = Path(str(metadata["workspace_agents_target"]))
    learned_target = Path(str(metadata["learned_reference_target"]))
    _validate_workspace_activation_restore_targets(
        runtime_paths,
        workspace_root,
        agents_target,
        learned_target,
    )
    _restore_snapshot_by_kind(
        kind=str(metadata["workspace_agents_kind"]),
        snapshot_path=_optional_path(metadata.get("workspace_agents_snapshot_path")),
        target=agents_target,
    )
    _restore_snapshot_by_kind(
        kind=str(metadata["learned_reference_kind"]),
        snapshot_path=_optional_path(metadata.get("learned_reference_snapshot_path")),
        target=learned_target,
    )


def _validate_workspace_activation_restore_targets(
    runtime_paths: RuntimePaths,
    workspace_root: Path,
    agents_target: Path,
    learned_target: Path,
) -> None:
    expected_agents = workspace_root / ".agents"
    if agents_target.resolve(strict=False) != expected_agents.resolve(strict=False):
        raise ValueError("workspace activation backup agents target mismatch")
    expected_learned = (
        runtime_paths.state / "recommendations" / "asahina-reference.md"
    )
    if learned_target.resolve(strict=False) != expected_learned.resolve(strict=False):
        raise ValueError("workspace activation backup learned reference target mismatch")


def _restore_snapshot_by_kind(
    *,
    kind: str,
    snapshot_path: Path | None,
    target: Path,
) -> None:
    if kind == "missing":
        _remove_path(target)
        return
    if snapshot_path is None:
        raise ValueError(f"snapshot path missing for {target}")
    if kind == "dir":
        _replace_directory_atomic(snapshot_path, target)
        return
    if kind == "file":
        _replace_file_atomic(snapshot_path, target)
        return
    raise ValueError(f"unknown snapshot kind: {kind}")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    if path.exists():
        path.unlink()


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


def _planned_archive_restore(
    runtime_paths: RuntimePaths,
) -> tuple[tuple[Path, Path], ...]:
    from sos.manifest import load_pack_manifest

    moves: list[tuple[Path, Path]] = []
    if not runtime_paths.packs.is_dir():
        return ()
    for manifest_path in sorted(runtime_paths.packs.glob("*.toml")):
        manifest = load_pack_manifest(manifest_path)
        for skill in manifest.skills:
            if skill.archived_source_path is None:
                continue
            if not skill.archived_source_path.is_dir():
                raise ValueError(
                    f"archive entry missing for {manifest.id}/{skill.name}; "
                    f"expected at {skill.archived_source_path}"
                )
            moves.append((skill.archived_source_path, skill.source_path))
    return tuple(moves)


def _planned_archive_restore_for_backup(
    record: BackupRecord,
    runtime_paths: RuntimePaths,
) -> tuple[tuple[Path, Path], ...]:
    entries = record.metadata.get("archive_restore_entries")
    if entries is None:
        return _planned_archive_restore(runtime_paths)
    if not isinstance(entries, list):
        raise ValueError("archive_restore_entries must be a list")

    moves: list[tuple[Path, Path]] = []
    target_keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("archive restore entry must be a table")
        pack_id = _safe_metadata_component(entry.get("pack_id"), "pack_id")
        skill_name = _safe_metadata_component(entry.get("skill_name"), "skill_name")
        archive_path = _required_metadata_path(entry.get("archive_path"), "archive_path")
        source_path = _required_metadata_path(entry.get("source_path"), "source_path")
        target_key = cross_platform_path_key(source_path)
        if target_key in target_keys:
            raise ValueError("archive restore target collision")
        target_keys.add(target_key)
        if not archive_path.is_dir():
            raise ValueError(
                f"archive entry missing for {pack_id}/{skill_name}; expected at {archive_path}"
            )
        moves.append((archive_path, source_path))
    return tuple(moves)


def _safe_metadata_component(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"archive restore entry {label} must be a string")
    try:
        return safe_component(value, label)
    except ValueError as error:
        raise ValueError(f"unsafe archive restore entry {label}: {value}") from error


def _required_metadata_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"archive restore entry {label} must be a path string")
    return Path(value)


def _restore_archive_moves(moves: tuple[tuple[Path, Path], ...]) -> None:
    from sos._archive import ArchiveMove, rollback_archive_moves

    journal: list[ArchiveMove] = []
    try:
        for source, target in moves:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            try:
                os.replace(source, target)
            except OSError:
                shutil.copytree(source, target)
                shutil.rmtree(source)
            journal.append(ArchiveMove(source=source, target=target))
    except Exception:
        rollback_archive_moves(tuple(journal))
        raise


def _rollback_restored_archive_moves(moves: tuple[tuple[Path, Path], ...]) -> None:
    rollback_moves = tuple((target, source) for source, target in moves)
    _restore_archive_moves(rollback_moves)


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
        metadata["config_snapshot_path"] = config_snapshot_path.as_posix()
    if vault_snapshot_path is not None:
        metadata["vault_snapshot_path"] = vault_snapshot_path.as_posix()
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
