from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sos.apply import ApplyResult
from sos.models import OperationKind, PackManifest, WriteOperation, WritePlan
from sos.pack_inspect import list_pack_manifests
from sos.paths import RuntimePaths
from sos.pointer import (
    render_workspace_asahina_skill,
    render_workspace_nagato_skill,
    render_workspace_pack_pointer,
)
from sos.recommendation_store import ensure_learned_reference_stub, learned_reference_path

_WORKSPACE_SKILL_ROOT_PARTS = (".agents", "skills")
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
) -> WritePlan:
    workspace_root_path = Path(workspace_root)
    workspace_skill_root = workspace_root_path / ".agents" / "skills"
    manifests = _selected_manifests(runtime_paths, pack_ids)
    operations = (
        _workspace_skill_operation(workspace_skill_root, "sos-nagato"),
        *tuple(_pointer_operation(workspace_skill_root, manifest) for manifest in manifests),
        _workspace_skill_operation(workspace_skill_root, "sos-asahina"),
        WriteOperation(
            OperationKind.WRITE_LEARNED_REFERENCE_STUB,
            target=learned_reference_path(runtime_paths),
        ),
    )
    return WritePlan(
        plan_id=_plan_id(runtime_paths, workspace_root_path, pack_ids),
        pack_ids=tuple(pack_ids),
        operations=operations,
        requires_apply=True,
    )


def apply_workspace_activation_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    *,
    workspace_root: str | Path,
    apply: bool,
) -> ApplyResult:
    validated = _validate_workspace_activation_plan(
        plan,
        runtime_paths,
        Path(workspace_root),
    )
    if not apply:
        return ApplyResult(status="planned", operations=plan.operations)

    snapshots, snapshot_root = _snapshot_targets(validated)
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
                message=f"{error}; rollback failed: {rollback_error}",
            )
        return ApplyResult(
            status="failed",
            operations=plan.operations,
            message=str(error),
        )
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)

    return ApplyResult(status="applied", operations=plan.operations)


def _plan_id(
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


def _workspace_skill_operation(workspace_skill_root: Path, skill_name: str) -> WriteOperation:
    safe_skill_name = _safe_pointer_skill(skill_name)
    return WriteOperation(
        OperationKind.WRITE_WORKSPACE_SKILL,
        target=workspace_skill_root / safe_skill_name / "SKILL.md",
        metadata={
            "workspace_skill_root": str(workspace_skill_root),
            "skill_name": safe_skill_name,
        },
    )


def _pointer_operation(workspace_skill_root: Path, manifest: PackManifest) -> WriteOperation:
    pointer_skill = _safe_pointer_skill(manifest.pointer_skill)
    return WriteOperation(
        OperationKind.WRITE_POINTER,
        target=workspace_skill_root / pointer_skill / "SKILL.md",
        metadata={
            "workspace_skill_root": str(workspace_skill_root),
            "pack_id": manifest.id,
            "pointer_skill": pointer_skill,
        },
    )


def _validate_workspace_activation_plan(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    expected_workspace_root: Path,
) -> _ValidatedWorkspacePlan:
    if not plan.requires_apply:
        raise ValueError("workspace activation plan must require apply")

    operations = plan.operations
    if len(operations) != len(plan.pack_ids) + 3:
        raise ValueError("workspace activation plan has unexpected operation count")

    _validate_operation_kinds(operations)
    workspace_skill_root = _workspace_skill_root_from_operation(operations[0])
    workspace_root = workspace_skill_root.parent.parent
    _validate_workspace_root_anchor(workspace_root, expected_workspace_root)
    expected_plan_id = _plan_id(runtime_paths, workspace_root, plan.pack_ids)
    if plan.plan_id != expected_plan_id:
        raise ValueError("workspace activation plan id mismatch")
    manifests = _selected_manifests(runtime_paths, plan.pack_ids)

    nagato_target = _validate_workspace_skill_operation(
        operations[0],
        workspace_skill_root,
        "sos-nagato",
    )
    pointer_operations = operations[1 : 1 + len(plan.pack_ids)]
    pointer_targets = _validate_pointer_operations(
        pointer_operations,
        workspace_skill_root,
        manifests,
    )
    asahina_target = _validate_workspace_skill_operation(
        operations[1 + len(plan.pack_ids)],
        workspace_skill_root,
        "sos-asahina",
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


def _workspace_skill_root_from_operation(operation: WriteOperation) -> Path:
    workspace_skill_root = Path(str(operation.metadata.get("workspace_skill_root", "")))
    if workspace_skill_root.name != _WORKSPACE_SKILL_ROOT_PARTS[-1]:
        raise ValueError("workspace activation plan must target workspace .agents skills root")
    if workspace_skill_root.parent.name != _WORKSPACE_SKILL_ROOT_PARTS[0]:
        raise ValueError("workspace activation plan must target workspace .agents skills root")
    return workspace_skill_root


def _validate_workspace_skill_operation(
    operation: WriteOperation,
    workspace_skill_root: Path,
    expected_skill_name: str,
) -> Path:
    if operation.kind != OperationKind.WRITE_WORKSPACE_SKILL:
        raise ValueError(f"unexpected operation kind: {operation.kind}")
    metadata_skill_name = str(operation.metadata.get("skill_name", ""))
    safe_skill_name = _safe_pointer_skill(metadata_skill_name)
    if safe_skill_name != expected_skill_name:
        raise ValueError(f"unexpected workspace skill: {safe_skill_name}")
    if _workspace_skill_root_from_operation(operation) != workspace_skill_root:
        raise ValueError("workspace skill root mismatch in operation metadata")
    target = _required_path(operation.target)
    _validate_workspace_skill_target(target, workspace_skill_root, safe_skill_name)
    return target


def _validate_pointer_operations(
    operations: tuple[WriteOperation, ...],
    workspace_skill_root: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[Path, ...]:
    if len(operations) != len(manifests):
        raise ValueError("workspace activation pointer operations do not match pack ids")

    targets: list[Path] = []
    for operation, manifest in zip(operations, manifests, strict=True):
        if operation.kind != OperationKind.WRITE_POINTER:
            raise ValueError(f"unexpected operation kind: {operation.kind}")
        if _workspace_skill_root_from_operation(operation) != workspace_skill_root:
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
