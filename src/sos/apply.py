from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sos._archive import ARCHIVE_DIR_NAME, ArchiveMove, rollback_archive_moves
from sos.active_namespace import validate_active_skill_namespace
from sos.backups import create_backup, record_claude_archive_restore_entries
from sos.codex_config import disable_skill_paths_with_backup
from sos.fingerprint import fingerprint_dir
from sos.fs_transaction import (
    PathSnapshot,
    remove_path,
    restore_snapshots,
    snapshot_paths,
    unique_paths,
)
from sos.host_adapter import HostAdapter, HostValidation, host_adapter_for
from sos.manifest import (
    load_registry,
    save_pack_manifest,
    save_registry,
    update_registry_after_apply,
    validate_registry,
)
from sos.models import (
    OperationKind,
    PackManifest,
    Registry,
    SkillEntry,
    WriteOperation,
    WritePlan,
)
from sos.path_safety import (
    ensure_under,
    reject_component_collisions,
    required_path,
    safe_component,
    safe_pointer_skill,
)
from sos.paths import RuntimePaths
from sos.plan_ops import operations_of_kind, single_operation
from sos.pointer import render_v1_active_skills
from sos.skill_fs import replace_skill_folder_atomic, validate_skill_folder


@dataclass(frozen=True)
class ApplyResult:
    status: str
    operations: tuple[WriteOperation, ...] = ()
    backup_id: str | None = None
    message: str = ""
    deleted_source_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "deleted_source_paths", tuple(self.deleted_source_paths))


@dataclass(frozen=True)
class _ValidatedPlan:
    manifests: tuple[PackManifest, ...]
    pointer_targets: tuple[Path, ...]
    disabled_skill_md_paths: tuple[Path, ...]
    delete_source_candidates: tuple["_DeleteSourceCandidate", ...]
    archive_operations: tuple[WriteOperation, ...] = ()


@dataclass(frozen=True)
class _DeleteSourceCandidate:
    path: Path
    pack_id: str
    skill_name: str


_OPERATION_PHASES = {
    OperationKind.BACKUP_CODEX_CONFIG: 0,
    OperationKind.BACKUP_VAULT: 0,
    OperationKind.COPY_SKILL: 1,
    OperationKind.WRITE_MANIFEST: 2,
    OperationKind.WRITE_REGISTRY: 3,
    OperationKind.WRITE_POINTER: 4,
    OperationKind.DISABLE_CODEX_SKILL: 5,
    OperationKind.MOVE_TO_ARCHIVE: 5,
    OperationKind.DELETE_SOURCE: 6,
    OperationKind.RESTORE_FROM_ARCHIVE: 7,
}


def apply_write_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    codex_config_path: str | Path,
    active_skill_root: str | Path,
    apply: bool,
    *,
    host: str = "codex",
    delete_source: bool = False,
    confirm_delete_source: str | None = None,
    delete_source_paths: tuple[str | Path, ...] | None = None,
) -> ApplyResult:
    if host not in {"codex", "claude"}:
        raise ValueError(f"unsupported host: {host}")
    if plan.host != host:
        raise ValueError(
            f"plan host {plan.host!r} does not match --host {host!r}"
        )
    config_path = Path(codex_config_path)
    active_root = Path(active_skill_root)
    adapter = host_adapter_for(host)
    validated = _validate_plan(plan, runtime_paths, config_path, active_root, adapter)
    source_deletion_paths = _validated_source_deletion_paths(
        validated.delete_source_candidates,
        apply=apply,
        delete_source=delete_source,
        confirm_delete_source=confirm_delete_source,
        selected_paths=delete_source_paths,
    )

    if not apply:
        return ApplyResult(status="planned", operations=plan.operations)

    backup = create_backup(
        runtime_paths,
        config_path,
        runtime_paths.vault,
        reason=f"apply write plan {plan.plan_id}",
    )
    snapshots, snapshot_root = _snapshot_apply_targets(
        plan,
        validated,
        config_path,
        source_deletion_paths,
    )
    archive_journal: list[ArchiveMove] = []

    try:
        for operation in operations_of_kind(plan, OperationKind.COPY_SKILL):
            replace_skill_folder_atomic(
                required_path(operation.source),
                required_path(operation.target),
            )

        archive_map = adapter.execute_archive_moves(plan, archive_journal)

        baselined_manifests = _with_initial_fingerprints(
            validated.manifests, archive_map=archive_map
        )
        for operation, manifest in zip(
            operations_of_kind(plan, OperationKind.WRITE_MANIFEST),
            baselined_manifests,
            strict=True,
        ):
            save_pack_manifest(required_path(operation.target), manifest)

        registry = update_registry_after_apply(
            Registry(),
            baselined_manifests,
            validated.pointer_targets,
            backup.backup_id,
        )
        validate_registry(registry)
        registry_operation = single_operation(plan, OperationKind.WRITE_REGISTRY)
        save_registry(required_path(registry_operation.target), registry)

        render_v1_active_skills(active_root, registry, baselined_manifests)

        adapter.execute_post_pointer_disable(
            plan,
            config_path,
            backup.config_path or (runtime_paths.backups / backup.backup_id / "config.toml"),
            validated.disabled_skill_md_paths,
        )

        for path in source_deletion_paths:
            remove_path(path)

        adapter.post_apply(runtime_paths, backup.backup_id, baselined_manifests)
    except Exception as error:
        rollback_message = ""
        try:
            rollback_archive_moves(tuple(archive_journal))
            restore_snapshots(snapshots)
        except Exception as rollback_error:
            rollback_message = f"; rollback failed: {rollback_error}"
        return ApplyResult(
            status="failed",
            operations=plan.operations,
            backup_id=backup.backup_id,
            message=f"{error}{rollback_message}",
        )
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)

    return ApplyResult(
        status="applied",
        operations=plan.operations,
        backup_id=backup.backup_id,
        deleted_source_paths=source_deletion_paths,
    )


def _with_initial_fingerprints(
    manifests: tuple[PackManifest, ...],
    *,
    archive_map: dict[Path, Path] | None = None,
) -> tuple[PackManifest, ...]:
    synced_at = datetime.now(timezone.utc).isoformat()
    mapping = archive_map or {}
    return tuple(
        replace(
            manifest,
            skills=tuple(
                replace(
                    skill,
                    last_source_fingerprint=fingerprint_dir(
                        mapping.get(skill.source_path, skill.source_path)
                    ),
                    last_vault_fingerprint=fingerprint_dir(skill.vault_path),
                    last_synced_at=synced_at,
                    archived_source_path=mapping.get(skill.source_path),
                )
                for skill in manifest.skills
            ),
        )
        for manifest in manifests
    )


def _snapshot_apply_targets(
    plan: WritePlan,
    validated: _ValidatedPlan,
    config_path: Path,
    source_deletion_paths: tuple[Path, ...],
) -> tuple[tuple[PathSnapshot, ...], Path]:
    targets = _unique_paths_for_apply(plan, validated, config_path, source_deletion_paths)
    return snapshot_paths(targets, prefix="sos-apply-rollback-")


def _unique_paths_for_apply(
    plan: WritePlan,
    validated: _ValidatedPlan,
    config_path: Path,
    source_deletion_paths: tuple[Path, ...],
) -> tuple[Path, ...]:
    return unique_paths(
        (
            *_rollback_target_paths(plan, validated),
            config_path,
            *source_deletion_paths,
        )
    )


def _rollback_target_paths(
    plan: WritePlan,
    validated: _ValidatedPlan,
) -> tuple[Path, ...]:
    return (
        *tuple(
            required_path(operation.target)
            for operation in operations_of_kind(plan, OperationKind.COPY_SKILL)
        ),
        *tuple(
            required_path(operation.target)
            for operation in operations_of_kind(plan, OperationKind.WRITE_MANIFEST)
        ),
        required_path(single_operation(plan, OperationKind.WRITE_REGISTRY).target),
        *tuple(pointer_target.parent for pointer_target in validated.pointer_targets),
    )


def _validate_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    config_path: Path,
    active_root: Path,
    adapter: HostAdapter,
) -> _ValidatedPlan:
    _validate_operation_kinds_and_order(plan.operations)
    _validate_host_operation_set(plan.operations, adapter.host)
    host_validation = adapter.validate_host_plan(
        plan, runtime_paths, config_path, active_root, _validated_manifests(plan, runtime_paths, active_root)
    )
    manifests = _validated_manifests(plan, runtime_paths, active_root)
    _validate_copy_operations(plan, manifests, active_root, runtime_paths)
    _validate_registry_operation(plan, runtime_paths, manifests)
    pointer_targets = _validate_pointer_operations(plan, active_root, manifests)
    delete_source_candidates = _validate_delete_candidates(plan, active_root, manifests, adapter)
    return _ValidatedPlan(
        manifests=manifests,
        pointer_targets=pointer_targets,
        disabled_skill_md_paths=host_validation.disabled_skill_md_paths,
        delete_source_candidates=delete_source_candidates,
        archive_operations=host_validation.archive_operations,
    )


def _validate_operation_kinds_and_order(operations: tuple[WriteOperation, ...]) -> None:
    current_phase = -1
    for operation in operations:
        if operation.kind not in _OPERATION_PHASES:
            raise ValueError(f"unexpected operation kind: {operation.kind}")
        phase = _OPERATION_PHASES[operation.kind]
        if phase < current_phase:
            raise ValueError(f"unexpected operation order at {operation.kind.value}")
        current_phase = phase


def _validate_host_operation_set(
    operations: tuple[WriteOperation, ...], host: str
) -> None:
    kinds = {operation.kind for operation in operations}
    codex_only = {OperationKind.BACKUP_CODEX_CONFIG, OperationKind.DISABLE_CODEX_SKILL}
    claude_only = {OperationKind.MOVE_TO_ARCHIVE}
    if host == "codex" and kinds & claude_only:
        raise ValueError(f"claude-only operations in codex plan: {sorted(k.value for k in kinds & claude_only)}")
    if host == "claude" and kinds & codex_only:
        raise ValueError(f"codex-only operations in claude plan: {sorted(k.value for k in kinds & codex_only)}")


def _validated_manifests(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    active_root: Path,
) -> tuple[PackManifest, ...]:
    manifests = tuple(
        _pack_manifest_from_metadata(_required_mapping(operation.metadata.get("manifest")))
        for operation in operations_of_kind(plan, OperationKind.WRITE_MANIFEST)
    )
    if tuple(manifest.id for manifest in manifests) != plan.pack_ids:
        raise ValueError("manifest pack ids do not match plan pack ids")

    for operation, manifest in zip(
        operations_of_kind(plan, OperationKind.WRITE_MANIFEST),
        manifests,
        strict=True,
    ):
        safe_component(manifest.id, "pack_id")
        safe_pointer_skill(manifest.pointer_skill)
        expected_target = runtime_paths.packs / f"{manifest.id}.toml"
        if required_path(operation.target) != expected_target:
            raise ValueError(f"manifest target does not match pack id: {manifest.id}")
        ensure_under(expected_target, runtime_paths.packs, "manifest target path")
        if manifest.vault_root is not None:
            ensure_under(manifest.vault_root, runtime_paths.vault, "manifest vault root")
        for skill in manifest.skills:
            safe_component(skill.name, "skill_name")
            ensure_under(skill.source_path, active_root, "manifest source path")
            expected_source_path = active_root / skill.name
            if skill.source_path.resolve(strict=False) != expected_source_path.resolve(
                strict=False
            ):
                raise ValueError(
                    "manifest source path does not match skill name: "
                    f"{skill.source_path} != {expected_source_path}"
                )
            ensure_under(skill.vault_path, runtime_paths.vault, "manifest vault path")
            validate_skill_folder(skill.source_path)

    pack_ids = tuple(manifest.id for manifest in manifests)
    reject_component_collisions(pack_ids, "pack_id")
    all_skill_names: list[str] = []
    for manifest in manifests:
        for skill in manifest.skills:
            all_skill_names.append(skill.name)
    reject_component_collisions(tuple(all_skill_names), "skill_name")

    pointer_skills = tuple(manifest.pointer_skill for manifest in manifests)
    reject_component_collisions(pointer_skills, "pointer_skill")
    validate_active_skill_namespace(
        active_root,
        source_skill_names=tuple(all_skill_names),
        pointer_skill_names=pointer_skills,
        managed_pointer_names=_previous_active_pointers(runtime_paths),
    )

    for manifest in manifests:
        if manifest.pointer_skill != f"sos-{manifest.id}":
            raise ValueError(
                f"pointer_skill {manifest.pointer_skill!r} does not match "
                f"expected sos-{manifest.id}"
            )

    return manifests


def _previous_active_pointers(runtime_paths: RuntimePaths) -> tuple[str, ...]:
    registry_path = runtime_paths.state / "registry.toml"
    if not registry_path.is_file():
        return ()
    return load_registry(registry_path).active_pointers


def _validate_copy_operations(
    plan: WritePlan,
    manifests: tuple[PackManifest, ...],
    active_root: Path,
    runtime_paths: RuntimePaths,
) -> None:
    expected = tuple(
        (skill.source_path, skill.vault_path)
        for manifest in manifests
        for skill in manifest.skills
    )
    actual = tuple(
        (required_path(operation.source), required_path(operation.target))
        for operation in operations_of_kind(plan, OperationKind.COPY_SKILL)
    )
    for source, target in actual:
        ensure_under(source, active_root, "copy source path")
        ensure_under(target, runtime_paths.vault, "copy target path")
        validate_skill_folder(source)
    if actual != expected:
        raise ValueError("copy operations do not match manifest skills")


def _validate_registry_operation(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    manifests: tuple[PackManifest, ...],
) -> None:
    operation = single_operation(plan, OperationKind.WRITE_REGISTRY)
    target = required_path(operation.target)
    if target != runtime_paths.state / "registry.toml":
        raise ValueError("registry target does not match runtime state path")
    ensure_under(target, runtime_paths.state, "registry target path")

    registry_data = _required_mapping(operation.metadata.get("registry"))
    registry_pack_ids = tuple(
        str(_required_mapping(pack).get("id"))
        for pack in registry_data.get("packs", ())
    )
    if registry_pack_ids != tuple(manifest.id for manifest in manifests):
        raise ValueError("registry packs do not match manifest operations")


def _validate_pointer_operations(
    plan: WritePlan,
    active_root: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[Path, ...]:
    expected_targets = (
        active_root / "sos-haruhi" / "SKILL.md",
        *tuple(active_root / manifest.pointer_skill / "SKILL.md" for manifest in manifests),
    )
    actual_targets = tuple(
        required_path(operation.target)
        for operation in operations_of_kind(plan, OperationKind.WRITE_POINTER)
    )
    if actual_targets != expected_targets:
        raise ValueError("pointer operations do not match expected active skills")

    for target in actual_targets:
        ensure_under(target, active_root, "pointer target path")
        if target.name != "SKILL.md":
            raise ValueError(f"pointer target must be SKILL.md: {target}")
        safe_pointer_skill(target.parent.name)
    return actual_targets


def _validate_archive_operations(
    plan: WritePlan,
    active_root: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[WriteOperation, ...]:
    expected = tuple(
        (skill.source_path, active_root / ARCHIVE_DIR_NAME / manifest.id / skill.name)
        for manifest in manifests
        for skill in manifest.skills
    )
    operations = operations_of_kind(plan, OperationKind.MOVE_TO_ARCHIVE)
    actual = tuple(
        (required_path(operation.source), required_path(operation.target))
        for operation in operations
    )

    if actual != expected:
        raise ValueError("archive operations do not match manifest skills")

    archive_root = active_root / ARCHIVE_DIR_NAME
    for operation, (source, target) in zip(operations, actual, strict=True):
        ensure_under(source, active_root, "archive source path")
        ensure_under(target, archive_root, "archive target path")
        if _is_plugin_cache_path(source):
            raise ValueError(f"refusing to archive source path inside plugin cache: {source}")
        if operation.metadata.get("host") != "claude":
            raise ValueError("archive operation metadata must declare host=claude")
    return operations


def _validate_delete_candidates(
    plan: WritePlan,
    active_root: Path,
    manifests: tuple[PackManifest, ...],
    adapter: HostAdapter,
) -> tuple[_DeleteSourceCandidate, ...]:
    expected = adapter.expected_delete_targets(active_root, manifests)
    actual: list[tuple[Path, str, str]] = []
    candidates: list[_DeleteSourceCandidate] = []
    for operation in operations_of_kind(plan, OperationKind.DELETE_SOURCE):
        target = required_path(operation.target)
        pack_id = str(operation.metadata.get("pack_id", ""))
        skill_name = str(operation.metadata.get("skill_name", ""))
        ensure_under(target, active_root, "delete source target path")
        if (
            operation.metadata.get("candidate") is not True
            or operation.metadata.get("active") is True
        ):
            raise ValueError("delete source operations must be inactive candidates in task 10")
        actual.append((target, pack_id, skill_name))
        candidates.append(
            _DeleteSourceCandidate(
                path=target,
                pack_id=pack_id,
                skill_name=skill_name,
            )
        )
    if tuple(actual) != expected:
        raise ValueError("delete source operations do not match manifest skills")
    return tuple(candidates)


def _validated_source_deletion_paths(
    candidates: tuple[_DeleteSourceCandidate, ...],
    *,
    apply: bool,
    delete_source: bool,
    confirm_delete_source: str | None,
    selected_paths: tuple[str | Path, ...] | None,
) -> tuple[Path, ...]:
    if confirm_delete_source is not None and not delete_source:
        raise ValueError("--confirm-delete-source requires --delete-source")
    if selected_paths is not None and not delete_source:
        raise ValueError("delete_source_paths requires delete_source")
    if not delete_source:
        return ()
    if not apply:
        raise ValueError("--delete-source requires --apply")
    if confirm_delete_source is None:
        raise ValueError("--delete-source requires --confirm-delete-source <pack-id>")

    candidates_by_path = {
        _path_key(candidate.path): candidate
        for candidate in candidates
    }
    exact_selection = selected_paths is not None
    selected = (
        tuple(
            candidate.path
            for candidate in candidates
            if candidate.pack_id == confirm_delete_source
        )
        if not exact_selection
        else tuple(Path(path) for path in selected_paths)
    )
    if not selected:
        raise ValueError("--confirm-delete-source must match a pack id in the write plan")

    deletion_paths: list[Path] = []
    for path in selected:
        candidate = candidates_by_path.get(_path_key(path))
        if candidate is None:
            if _is_claude_specific_path(path):
                raise ValueError(
                    "Claude-specific paths require exact source paths selected "
                    "in the write plan"
                )
            raise ValueError(
                "delete source path is not present in write plan deletion candidates"
            )
        if candidate.pack_id != confirm_delete_source:
            raise ValueError("delete source confirmation does not match candidate pack id")
        if _is_plugin_cache_path(candidate.path):
            raise ValueError(f"refusing to delete source path inside plugin cache: {candidate.path}")
        if (
            _is_claude_specific_path(candidate.path)
            and not _is_archive_path(candidate.path)
            and not exact_selection
        ):
            raise ValueError(
                "Claude-specific source paths require exact deletion path selection"
            )
        deletion_paths.append(candidate.path)
    return unique_paths(tuple(deletion_paths))


def _path_key(path: Path) -> str:
    return str(path.resolve(strict=False))


def _is_plugin_cache_path(path: Path) -> bool:
    parts = path.resolve(strict=False).parts
    return any(
        parts[index : index + 3] == (".codex", "plugins", "cache")
        or parts[index : index + 3] == (".claude", "plugins", "cache")
        for index in range(len(parts) - 2)
    )


def _is_claude_specific_path(path: Path) -> bool:
    return ".claude" in path.resolve(strict=False).parts


def _is_archive_path(path: Path) -> bool:
    from sos._archive import ARCHIVE_DIR_NAME
    return ARCHIVE_DIR_NAME in path.resolve(strict=False).parts


def _pack_manifest_from_metadata(data: Mapping[str, Any]) -> PackManifest:
    paths = _optional_mapping(data.get("paths"))
    vault_root = paths.get("vault_root") if paths is not None else None
    return PackManifest(
        id=str(data["id"]),
        display_name=str(data["display_name"]),
        aliases=tuple(str(alias) for alias in data.get("aliases", ())),
        description=str(data.get("description", "")),
        pointer_skill=str(data["pointer_skill"]),
        sync_policy=str(data.get("sync_policy", "clean-auto")),
        vault_root=Path(str(vault_root)) if vault_root else None,
        skills=tuple(
            _skill_entry_from_metadata(_required_mapping(skill))
            for skill in data.get("skills", ())
        ),
        triggers=tuple(
            {str(key): str(value) for key, value in _required_mapping(trigger).items()}
            for trigger in data.get("triggers", ())
        ),
        host=str(data.get("host", "codex")),
    )


def _skill_entry_from_metadata(data: Mapping[str, Any]) -> SkillEntry:
    return SkillEntry(
        name=str(data["name"]),
        source_path=Path(str(data["source_path"])),
        vault_path=Path(str(data["vault_path"])),
        origin=str(data.get("origin", "")),
        enabled_before_apply=bool(data.get("enabled_before_apply", True)),
        last_source_fingerprint=str(data.get("last_source_fingerprint", "")),
        last_vault_fingerprint=str(data.get("last_vault_fingerprint", "")),
        last_synced_at=str(data.get("last_synced_at", "")),
        description=str(data.get("description", "")),
    )


def _required_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping metadata")
    return value


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _required_mapping(value)
