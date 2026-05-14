from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sos.apply import ApplyResult
from sos.backups import create_workspace_activation_backup
from sos.host_paths import validate_host, workspace_skill_root_for_host
from sos.models import OperationKind, PackManifest, WriteOperation, WritePlan
from sos.pack_inspect import list_pack_manifests
from sos.paths import RuntimePaths
from sos.pointer import (
    render_workspace_asahina_skill,
    render_workspace_nagato_skill,
    render_workspace_pack_pointer,
)
from sos.recommendation_store import ensure_learned_reference_stub, learned_reference_path

_WORKSPACE_SKILL_NAMES = ("sos-nagato", "sos-asahina")
render_nagato_skill = render_workspace_nagato_skill
render_pack_pointer = render_workspace_pack_pointer
render_asahina_skill = render_workspace_asahina_skill


@dataclass(frozen=True)
class _ValidatedWorkspacePlan:
    workspace_root: Path
    workspace_skill_root: Path
    nagato_target: Path
    asahina_target: Path
    pointer_targets: tuple[Path, ...]
    manifests: tuple[PackManifest, ...]
    learned_reference_target: Path


@dataclass(frozen=True)
class _PathSnapshot:
    path: Path
    kind: str
    backup_path: Path | None = None


def build_workspace_activation_plan(
    runtime_paths: RuntimePaths,
    workspace_root: str | Path,
    pack_ids: tuple[str, ...],
    *,
    host: str = "codex",
) -> WritePlan:
    safe_host = validate_host(host)
    workspace_root_path = _workspace_root_path(workspace_root)
    workspace_skill_root = workspace_skill_root_for_host(workspace_root_path, safe_host)
    manifests = _selected_manifests(runtime_paths, pack_ids)
    operations = (
        _workspace_skill_operation(workspace_skill_root, "sos-nagato", safe_host),
        *tuple(_pointer_operation(workspace_skill_root, manifest, safe_host) for manifest in manifests),
        _workspace_skill_operation(workspace_skill_root, "sos-asahina", safe_host),
        WriteOperation(
            OperationKind.WRITE_LEARNED_REFERENCE_STUB,
            target=learned_reference_path(runtime_paths),
        ),
    )
    return WritePlan(
        plan_id=_plan_id(runtime_paths, workspace_root_path, pack_ids, safe_host),
        pack_ids=tuple(pack_ids),
        operations=operations,
        requires_apply=True,
        host=safe_host,
    )


def apply_workspace_activation_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    *,
    workspace_root: str | Path,
    apply: bool,
    host: str | None = None,
) -> ApplyResult:
    effective_host = plan.host if host is None else validate_host(host)
    if effective_host != plan.host:
        raise ValueError(
            f"plan host {plan.host!r} does not match --host {effective_host!r}"
        )
    validated = _validate_workspace_activation_plan(
        plan,
        runtime_paths,
        _workspace_root_path(workspace_root),
        effective_host,
    )
    if not apply:
        return ApplyResult(status="planned", operations=plan.operations)

    backup = create_workspace_activation_backup(
        runtime_paths,
        validated.workspace_root,
        validated.workspace_skill_root.parent,
        validated.learned_reference_target,
        reason="workspace activation apply",
        host=effective_host,
    )
    try:
        snapshots, snapshot_root = _snapshot_targets(validated)
    except Exception as error:
        return ApplyResult(
            status="failed",
            operations=plan.operations,
            backup_id=backup.backup_id,
            message=f"snapshot failed: {error}",
        )
    try:
        render_nagato_skill(
            validated.nagato_target,
            runtime_root=runtime_paths.root,
            workspace_root=validated.workspace_root,
        )
        for target, manifest in zip(validated.pointer_targets, validated.manifests, strict=True):
            render_pack_pointer(target, manifest)
        render_asahina_skill(validated.asahina_target, runtime_root=runtime_paths.root)
        ensure_learned_reference_stub(runtime_paths, apply=True)
    except Exception as error:
        try:
            _restore_snapshots(snapshots)
        except Exception as rollback_error:
            return ApplyResult(
                status="failed",
                operations=plan.operations,
                backup_id=backup.backup_id,
                message=f"{error}; rollback failed: {rollback_error}",
            )
        return ApplyResult(
            status="failed",
            operations=plan.operations,
            backup_id=backup.backup_id,
            message=str(error),
        )
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)

    return ApplyResult(
        status="applied",
        operations=plan.operations,
        backup_id=backup.backup_id,
    )


def _plan_id(
    runtime_paths: RuntimePaths,
    workspace_root: Path,
    pack_ids: tuple[str, ...],
    host: str,
) -> str:
    payload = {
        "version": 1,
        "host": host,
        "runtime_root": str(runtime_paths.root),
        "workspace_root": str(workspace_root),
        "pack_ids": list(pack_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"workspace-activation-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _legacy_codex_plan_id(
    runtime_paths: RuntimePaths,
    workspace_root: Path,
    pack_ids: tuple[str, ...],
) -> str:
    payload = {
        "version": 1,
        "runtime_root": str(runtime_paths.root),
        "workspace_root": str(workspace_root),
        "pack_ids": list(pack_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"workspace-activation-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _workspace_root_path(workspace_root: str | Path) -> Path:
    return Path(workspace_root).expanduser()


def _selected_manifests(
    runtime_paths: RuntimePaths,
    pack_ids: tuple[str, ...],
) -> tuple[PackManifest, ...]:
    manifests_by_id = {manifest.id: manifest for manifest in list_pack_manifests(runtime_paths)}
    selected: list[PackManifest] = []
    for pack_id in pack_ids:
        safe_pack_id = _safe_component(pack_id, "pack_id")
        manifest = manifests_by_id.get(safe_pack_id)
        if manifest is None:
            raise ValueError(f"unknown pack: {pack_id}")
        _safe_pointer_skill(manifest.pointer_skill)
        selected.append(manifest)
    return tuple(selected)


def _workspace_skill_operation(
    workspace_skill_root: Path,
    skill_name: str,
    host: str,
) -> WriteOperation:
    safe_skill_name = _safe_pointer_skill(skill_name)
    return WriteOperation(
        OperationKind.WRITE_WORKSPACE_SKILL,
        target=workspace_skill_root / safe_skill_name / "SKILL.md",
        metadata={
            "workspace_skill_root": str(workspace_skill_root),
            "skill_name": safe_skill_name,
            "host": host,
        },
    )


def _pointer_operation(
    workspace_skill_root: Path,
    manifest: PackManifest,
    host: str,
) -> WriteOperation:
    pointer_skill = _safe_pointer_skill(manifest.pointer_skill)
    return WriteOperation(
        OperationKind.WRITE_POINTER,
        target=workspace_skill_root / pointer_skill / "SKILL.md",
        metadata={
            "workspace_skill_root": str(workspace_skill_root),
            "pack_id": manifest.id,
            "pointer_skill": pointer_skill,
            "host": host,
        },
    )


def _validate_workspace_activation_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    expected_workspace_root: Path,
    host: str,
) -> _ValidatedWorkspacePlan:
    safe_host = validate_host(host)
    if plan.host != safe_host:
        raise ValueError(f"plan host {plan.host!r} does not match --host {safe_host!r}")
    if not plan.requires_apply:
        raise ValueError("workspace activation plan must require apply")

    operations = plan.operations
    if len(operations) != len(plan.pack_ids) + 3:
        raise ValueError("workspace activation plan has unexpected operation count")

    _validate_operation_kinds(operations)
    workspace_skill_root = _workspace_skill_root_from_operation(operations[0], safe_host)
    workspace_root = workspace_skill_root.parent.parent
    _validate_workspace_root_anchor(workspace_root, expected_workspace_root)
    expected_skill_root = workspace_skill_root_for_host(expected_workspace_root, safe_host)
    if _normalized_path(workspace_skill_root) != _normalized_path(expected_skill_root):
        raise ValueError(
            f"workspace activation plan must target workspace {expected_skill_root.parent.name} skills root"
        )
    expected_plan_id = _plan_id(runtime_paths, workspace_root, plan.pack_ids, safe_host)
    if plan.plan_id != expected_plan_id and not _matches_legacy_codex_plan_id(
        plan,
        runtime_paths,
        workspace_root,
        safe_host,
    ):
        raise ValueError("workspace activation plan id mismatch")
    manifests = _selected_manifests(runtime_paths, plan.pack_ids)

    nagato_target = _validate_workspace_skill_operation(
        operations[0],
        workspace_skill_root,
        "sos-nagato",
        host=safe_host,
    )
    pointer_operations = operations[1 : 1 + len(plan.pack_ids)]
    pointer_targets = _validate_pointer_operations(
        pointer_operations,
        workspace_skill_root,
        manifests,
        host=safe_host,
    )
    asahina_target = _validate_workspace_skill_operation(
        operations[1 + len(plan.pack_ids)],
        workspace_skill_root,
        "sos-asahina",
        host=safe_host,
    )
    learned_operation = operations[2 + len(plan.pack_ids)]
    learned_target = learned_reference_path(runtime_paths)
    if learned_operation.kind != OperationKind.WRITE_LEARNED_REFERENCE_STUB:
        raise ValueError(f"unexpected operation kind: {learned_operation.kind}")
    if _required_path(learned_operation.target) != learned_target:
        raise ValueError("learned reference stub target does not match runtime path")

    return _ValidatedWorkspacePlan(
        workspace_root=workspace_root,
        workspace_skill_root=workspace_skill_root,
        nagato_target=nagato_target,
        asahina_target=asahina_target,
        pointer_targets=pointer_targets,
        manifests=manifests,
        learned_reference_target=learned_target,
    )


def _matches_legacy_codex_plan_id(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    workspace_root: Path,
    host: str,
) -> bool:
    if host != "codex":
        return False
    if any("host" in operation.metadata for operation in plan.operations):
        return False
    expected_plan_id = _legacy_codex_plan_id(runtime_paths, workspace_root, plan.pack_ids)
    return plan.plan_id == expected_plan_id


def _validate_workspace_root_anchor(
    plan_workspace_root: Path,
    expected_workspace_root: Path,
) -> None:
    if _normalized_path(plan_workspace_root) != _normalized_path(expected_workspace_root):
        raise ValueError("workspace activation plan workspace root does not match")


def _normalized_path(path: Path) -> Path:
    return path.resolve(strict=False)


def _validate_operation_kinds(operations: tuple[WriteOperation, ...]) -> None:
    allowed = {
        OperationKind.WRITE_WORKSPACE_SKILL,
        OperationKind.WRITE_POINTER,
        OperationKind.WRITE_LEARNED_REFERENCE_STUB,
    }
    for operation in operations:
        if operation.kind not in allowed:
            raise ValueError(f"unexpected operation kind: {operation.kind}")


def _workspace_skill_root_from_operation(operation: WriteOperation, host: str) -> Path:
    safe_host = validate_host(host)
    workspace_skill_root = Path(str(operation.metadata.get("workspace_skill_root", "")))
    expected_root = workspace_skill_root_for_host(workspace_skill_root.parent.parent, safe_host)
    if _normalized_path(workspace_skill_root) != _normalized_path(expected_root):
        raise ValueError(
            f"workspace activation plan must target workspace {expected_root.parent.name} skills root"
        )
    metadata_host = operation.metadata.get("host")
    if metadata_host is not None and metadata_host != safe_host:
        raise ValueError(f"workspace activation operation host mismatch: {metadata_host!r}")
    return workspace_skill_root


def _validate_workspace_skill_operation(
    operation: WriteOperation,
    workspace_skill_root: Path,
    expected_skill_name: str,
    *,
    host: str,
) -> Path:
    if operation.kind != OperationKind.WRITE_WORKSPACE_SKILL:
        raise ValueError(f"unexpected operation kind: {operation.kind}")
    metadata_skill_name = str(operation.metadata.get("skill_name", ""))
    safe_skill_name = _safe_pointer_skill(metadata_skill_name)
    if safe_skill_name != expected_skill_name:
        raise ValueError(f"unexpected workspace skill: {safe_skill_name}")
    if _workspace_skill_root_from_operation(operation, host) != workspace_skill_root:
        raise ValueError("workspace skill root mismatch in operation metadata")
    target = _required_path(operation.target)
    _validate_workspace_skill_target(target, workspace_skill_root, safe_skill_name)
    return target


def _validate_pointer_operations(
    operations: tuple[WriteOperation, ...],
    workspace_skill_root: Path,
    manifests: tuple[PackManifest, ...],
    *,
    host: str,
) -> tuple[Path, ...]:
    if len(operations) != len(manifests):
        raise ValueError("workspace activation pointer operations do not match pack ids")

    targets: list[Path] = []
    for operation, manifest in zip(operations, manifests, strict=True):
        if operation.kind != OperationKind.WRITE_POINTER:
            raise ValueError(f"unexpected operation kind: {operation.kind}")
        if _workspace_skill_root_from_operation(operation, host) != workspace_skill_root:
            raise ValueError("workspace pointer root mismatch in operation metadata")
        pack_id = str(operation.metadata.get("pack_id", ""))
        if _safe_component(pack_id, "pack_id") != manifest.id:
            raise ValueError("workspace pointer pack id does not match selected pack")
        pointer_skill = str(operation.metadata.get("pointer_skill", ""))
        if _safe_pointer_skill(pointer_skill) != manifest.pointer_skill:
            raise ValueError("workspace pointer skill does not match runtime manifest")
        target = _required_path(operation.target)
        _validate_workspace_skill_target(target, workspace_skill_root, pointer_skill)
        targets.append(target)
    return tuple(targets)


def _validate_workspace_skill_target(
    target: Path,
    workspace_skill_root: Path,
    expected_skill_name: str,
) -> None:
    _ensure_under(target, workspace_skill_root, "workspace skill target path")
    if target.name != "SKILL.md":
        raise ValueError(f"workspace skill target must be SKILL.md: {target}")
    skill_name = target.parent.name
    if _safe_pointer_skill(skill_name) != expected_skill_name:
        raise ValueError(f"workspace skill target does not match skill name: {target}")


def _snapshot_targets(
    validated: _ValidatedWorkspacePlan,
) -> tuple[tuple[_PathSnapshot, ...], Path]:
    snapshot_root = Path(tempfile.mkdtemp(prefix="sos-workspace-activation-"))
    rollback_paths = _unique_paths(
        (
            validated.workspace_skill_root.parent,
            validated.learned_reference_target.parent,
        )
    )
    snapshots = tuple(
        _snapshot_path(path, snapshot_root, index)
        for index, path in enumerate(rollback_paths)
    )
    return snapshots, snapshot_root


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
        resolved = str(path.resolve(strict=False))
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return tuple(unique)


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
