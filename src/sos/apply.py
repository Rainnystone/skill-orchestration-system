from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sos.backups import create_backup
from sos.codex_config import disable_skill_paths_with_backup
from sos.manifest import (
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
from sos.paths import RuntimePaths
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


@dataclass(frozen=True)
class _DeleteSourceCandidate:
    path: Path
    pack_id: str
    skill_name: str


@dataclass(frozen=True)
class _PathSnapshot:
    path: Path
    kind: str
    backup_path: Path | None = None


_OPERATION_PHASES = {
    OperationKind.BACKUP_CODEX_CONFIG: 0,
    OperationKind.BACKUP_VAULT: 0,
    OperationKind.COPY_SKILL: 1,
    OperationKind.WRITE_MANIFEST: 2,
    OperationKind.WRITE_REGISTRY: 3,
    OperationKind.WRITE_POINTER: 4,
    OperationKind.DISABLE_CODEX_SKILL: 5,
    OperationKind.DELETE_SOURCE: 6,
}


def apply_write_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    codex_config_path: str | Path,
    active_skill_root: str | Path,
    apply: bool,
    *,
    delete_source: bool = False,
    confirm_delete_source: str | None = None,
    delete_source_paths: tuple[str | Path, ...] | None = None,
) -> ApplyResult:
    config_path = Path(codex_config_path)
    active_root = Path(active_skill_root)
    validated = _validate_plan(plan, runtime_paths, config_path, active_root)
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

    try:
        for operation in _operations_of_kind(plan, OperationKind.COPY_SKILL):
            replace_skill_folder_atomic(
                _required_path(operation.source),
                _required_path(operation.target),
            )

        for operation, manifest in zip(
            _operations_of_kind(plan, OperationKind.WRITE_MANIFEST),
            validated.manifests,
            strict=True,
        ):
            save_pack_manifest(_required_path(operation.target), manifest)

        registry = update_registry_after_apply(
            Registry(),
            validated.manifests,
            validated.pointer_targets,
            backup.backup_id,
        )
        validate_registry(registry)
        registry_operation = _single_operation(plan, OperationKind.WRITE_REGISTRY)
        save_registry(_required_path(registry_operation.target), registry)

        render_v1_active_skills(active_root, registry, validated.manifests)

        config_backup_path = backup.config_path or (
            runtime_paths.backups / backup.backup_id / "config.toml"
        )
        disable_skill_paths_with_backup(
            config_path,
            validated.disabled_skill_md_paths,
            backup_path=config_backup_path,
            apply=True,
        )

        for path in source_deletion_paths:
            _remove_path(path)
    except Exception as error:
        rollback_message = ""
        try:
            _restore_snapshots(snapshots)
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


def _snapshot_apply_targets(
    plan: WritePlan,
    validated: _ValidatedPlan,
    config_path: Path,
    source_deletion_paths: tuple[Path, ...],
) -> tuple[tuple[_PathSnapshot, ...], Path]:
    snapshot_root = Path(tempfile.mkdtemp(prefix="sos-apply-rollback-"))
    snapshots = tuple(
        _snapshot_path(path, snapshot_root, index)
        for index, path in enumerate(
            _unique_paths(
                (
                    *_rollback_target_paths(plan, validated),
                    config_path,
                    *source_deletion_paths,
                )
            )
        )
    )
    return snapshots, snapshot_root


def _rollback_target_paths(
    plan: WritePlan,
    validated: _ValidatedPlan,
) -> tuple[Path, ...]:
    return (
        *tuple(
            _required_path(operation.target)
            for operation in _operations_of_kind(plan, OperationKind.COPY_SKILL)
        ),
        *tuple(
            _required_path(operation.target)
            for operation in _operations_of_kind(plan, OperationKind.WRITE_MANIFEST)
        ),
        _required_path(_single_operation(plan, OperationKind.WRITE_REGISTRY).target),
        *tuple(pointer_target.parent for pointer_target in validated.pointer_targets),
    )


def _snapshot_path(path: Path, snapshot_root: Path, index: int) -> _PathSnapshot:
    backup_path = snapshot_root / str(index)
    if path.is_dir():
        shutil.copytree(path, backup_path)
        return _PathSnapshot(path=path, kind="dir", backup_path=backup_path)
    if path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        return _PathSnapshot(path=path, kind="file", backup_path=backup_path)
    return _PathSnapshot(path=path, kind="missing")


def _restore_snapshots(snapshots: tuple[_PathSnapshot, ...]) -> None:
    for snapshot in reversed(snapshots):
        _restore_snapshot(snapshot)


def _restore_snapshot(snapshot: _PathSnapshot) -> None:
    if snapshot.kind == "missing":
        _remove_path(snapshot.path)
        return
    if snapshot.backup_path is None:
        raise ValueError(f"snapshot backup path missing for {snapshot.path}")

    _remove_path(snapshot.path)
    snapshot.path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.kind == "dir":
        shutil.copytree(snapshot.backup_path, snapshot.path)
        return
    if snapshot.kind == "file":
        shutil.copy2(snapshot.backup_path, snapshot.path)
        return
    raise ValueError(f"unknown snapshot kind: {snapshot.kind}")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    if path.exists():
        path.unlink()


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def _validate_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    config_path: Path,
    active_root: Path,
) -> _ValidatedPlan:
    _validate_operation_kinds_and_order(plan.operations)
    _validate_backup_operations(plan, runtime_paths, config_path)
    manifests = _validated_manifests(plan, runtime_paths, active_root)
    _validate_copy_operations(plan, manifests, active_root, runtime_paths)
    _validate_registry_operation(plan, runtime_paths, manifests)
    pointer_targets = _validate_pointer_operations(plan, active_root, manifests)
    disabled_skill_md_paths = _validate_disable_operations(
        plan,
        active_root,
        config_path,
        manifests,
    )
    delete_source_candidates = _validate_delete_candidates(plan, active_root, manifests)
    return _ValidatedPlan(
        manifests=manifests,
        pointer_targets=pointer_targets,
        disabled_skill_md_paths=disabled_skill_md_paths,
        delete_source_candidates=delete_source_candidates,
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


def _validate_backup_operations(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    config_path: Path,
) -> None:
    backup_config = _single_operation(plan, OperationKind.BACKUP_CODEX_CONFIG)
    backup_vault = _single_operation(plan, OperationKind.BACKUP_VAULT)

    if _required_path(backup_config.source) != config_path:
        raise ValueError("backup config source does not match codex_config_path")
    _ensure_under(
        _required_path(backup_config.target),
        runtime_paths.backups,
        "config backup target path",
    )
    if _required_path(backup_vault.source) != runtime_paths.vault:
        raise ValueError("backup vault source does not match runtime vault")
    _ensure_under(
        _required_path(backup_vault.target),
        runtime_paths.backups,
        "vault backup target path",
    )


def _validated_manifests(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    active_root: Path,
) -> tuple[PackManifest, ...]:
    manifests = tuple(
        _pack_manifest_from_metadata(_required_mapping(operation.metadata.get("manifest")))
        for operation in _operations_of_kind(plan, OperationKind.WRITE_MANIFEST)
    )
    if tuple(manifest.id for manifest in manifests) != plan.pack_ids:
        raise ValueError("manifest pack ids do not match plan pack ids")

    for operation, manifest in zip(
        _operations_of_kind(plan, OperationKind.WRITE_MANIFEST),
        manifests,
        strict=True,
    ):
        _safe_component(manifest.id, "pack_id")
        _safe_pointer_skill(manifest.pointer_skill)
        expected_target = runtime_paths.packs / f"{manifest.id}.toml"
        if _required_path(operation.target) != expected_target:
            raise ValueError(f"manifest target does not match pack id: {manifest.id}")
        _ensure_under(expected_target, runtime_paths.packs, "manifest target path")
        if manifest.vault_root is not None:
            _ensure_under(manifest.vault_root, runtime_paths.vault, "manifest vault root")
        for skill in manifest.skills:
            _safe_component(skill.name, "skill_name")
            _ensure_under(skill.source_path, active_root, "manifest source path")
            _ensure_under(skill.vault_path, runtime_paths.vault, "manifest vault path")
            validate_skill_folder(skill.source_path)
    return manifests


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
        (_required_path(operation.source), _required_path(operation.target))
        for operation in _operations_of_kind(plan, OperationKind.COPY_SKILL)
    )
    for source, target in actual:
        _ensure_under(source, active_root, "copy source path")
        _ensure_under(target, runtime_paths.vault, "copy target path")
        validate_skill_folder(source)
    if actual != expected:
        raise ValueError("copy operations do not match manifest skills")


def _validate_registry_operation(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    manifests: tuple[PackManifest, ...],
) -> None:
    operation = _single_operation(plan, OperationKind.WRITE_REGISTRY)
    target = _required_path(operation.target)
    if target != runtime_paths.state / "registry.toml":
        raise ValueError("registry target does not match runtime state path")
    _ensure_under(target, runtime_paths.state, "registry target path")

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
        _required_path(operation.target)
        for operation in _operations_of_kind(plan, OperationKind.WRITE_POINTER)
    )
    if actual_targets != expected_targets:
        raise ValueError("pointer operations do not match expected active skills")

    for target in actual_targets:
        _ensure_under(target, active_root, "pointer target path")
        if target.name != "SKILL.md":
            raise ValueError(f"pointer target must be SKILL.md: {target}")
        _safe_pointer_skill(target.parent.name)
    return actual_targets


def _validate_disable_operations(
    plan: WritePlan,
    active_root: Path,
    config_path: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[Path, ...]:
    expected_paths = tuple(
        skill.source_path / "SKILL.md"
        for manifest in manifests
        for skill in manifest.skills
    )
    operations = _operations_of_kind(plan, OperationKind.DISABLE_CODEX_SKILL)
    actual_paths = tuple(_required_path(operation.source) for operation in operations)
    if actual_paths != expected_paths:
        raise ValueError("config disable operations do not match manifest skills")

    for operation, skill_md_path in zip(operations, actual_paths, strict=True):
        _ensure_under(skill_md_path, active_root, "config disable source path")
        if _required_path(operation.target) != config_path:
            raise ValueError("config disable target does not match codex_config_path")
        metadata_path = operation.metadata.get("skill_md_path")
        if metadata_path is not None and Path(str(metadata_path)) != skill_md_path:
            raise ValueError("config disable metadata path does not match source")
    return actual_paths


def _validate_delete_candidates(
    plan: WritePlan,
    active_root: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[_DeleteSourceCandidate, ...]:
    expected = tuple(
        (skill.source_path, manifest.id, skill.name)
        for manifest in manifests
        for skill in manifest.skills
    )
    actual: list[tuple[Path, str, str]] = []
    candidates: list[_DeleteSourceCandidate] = []
    for operation in _operations_of_kind(plan, OperationKind.DELETE_SOURCE):
        target = _required_path(operation.target)
        pack_id = str(operation.metadata.get("pack_id", ""))
        skill_name = str(operation.metadata.get("skill_name", ""))
        _ensure_under(target, active_root, "delete source target path")
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
        if _is_claude_specific_path(candidate.path) and not exact_selection:
            raise ValueError(
                "Claude-specific source paths require exact deletion path selection"
            )
        deletion_paths.append(candidate.path)
    return _unique_paths(tuple(deletion_paths))


def _path_key(path: Path) -> str:
    return str(path.resolve(strict=False))


def _is_plugin_cache_path(path: Path) -> bool:
    parts = path.resolve(strict=False).parts
    return any(
        parts[index : index + 3] == (".codex", "plugins", "cache")
        for index in range(len(parts) - 2)
    )


def _is_claude_specific_path(path: Path) -> bool:
    return ".claude" in path.resolve(strict=False).parts


def _operations_of_kind(
    plan: WritePlan,
    kind: OperationKind,
) -> tuple[WriteOperation, ...]:
    return tuple(operation for operation in plan.operations if operation.kind == kind)


def _single_operation(plan: WritePlan, kind: OperationKind) -> WriteOperation:
    operations = _operations_of_kind(plan, kind)
    if len(operations) != 1:
        raise ValueError(f"expected exactly one {kind.value} operation")
    return operations[0]


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
    )


def _required_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping metadata")
    return value


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _required_mapping(value)


def _required_path(path: Path | None) -> Path:
    if path is None:
        raise ValueError("operation path is required")
    return path


def _safe_component(value: str, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
        or Path(value).name != value
    ):
        raise ValueError(f"unsafe {label}: {value}")
    return value


def _safe_pointer_skill(value: str) -> str:
    _safe_component(value, "pointer_skill")
    if not value.startswith("sos-"):
        raise ValueError(f"unsafe pointer_skill: {value}")
    return value


def _ensure_under(path: Path, root: Path, label: str) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root):
        return
    raise ValueError(f"{label} escapes expected root: {path}")
