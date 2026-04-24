from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from sos.fingerprint import fingerprint_dir
from sos.manifest import load_pack_manifest, save_pack_manifest
from sos.models import ActivationResult, OperationKind, PackManifest, SkillEntry, WriteOperation
from sos.skill_fs import replace_skill_folder_atomic, validate_skill_folder


@dataclass(frozen=True)
class SyncPlan:
    manifest_path: Path
    pack_id: str
    status: str
    manifest: PackManifest
    operations: tuple[WriteOperation, ...] = ()
    messages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "messages", tuple(self.messages))


def activate_pack(manifest_path: str | Path, sync_policy: str = "clean-auto") -> ActivationResult:
    plan = plan_pack_sync(manifest_path)
    if sync_policy != "clean-auto":
        return ActivationResult(
            status="unsupported-sync-policy",
            pack_id=plan.pack_id,
            manifest_path=plan.manifest_path,
            messages=(f"unsupported sync policy: {sync_policy}",),
        )
    if plan.status == "synced":
        return apply_pack_sync(plan, apply=True)
    return apply_pack_sync(plan, apply=False)


def plan_pack_sync(manifest_path: str | Path) -> SyncPlan:
    path = Path(manifest_path)
    manifest = load_pack_manifest(path)

    stale_messages: list[str] = []
    conflict_messages: list[str] = []
    sync_operations: list[WriteOperation] = []

    for skill in manifest.skills:
        vault_path_error = _validate_vault_path(manifest, skill)
        if vault_path_error is not None:
            conflict_messages.append(vault_path_error)
            continue

        source_fingerprint, source_error = _fingerprint_skill(skill.source_path)
        if source_error is not None:
            stale_messages.append(
                f"source missing or invalid for {skill.name}: {source_error}"
            )
            continue

        vault_fingerprint, vault_error = _fingerprint_skill(skill.vault_path)
        source_changed = source_fingerprint != skill.last_source_fingerprint
        vault_changed = (
            vault_error is not None
            or vault_fingerprint != skill.last_vault_fingerprint
        )

        if source_changed and not vault_changed:
            sync_operations.append(
                WriteOperation(
                    OperationKind.COPY_SKILL,
                    source=skill.source_path,
                    target=skill.vault_path,
                    metadata={"skill_name": skill.name},
                )
            )
            continue

        if source_changed or vault_changed:
            conflict_messages.append(_conflict_message(skill, source_changed, vault_error))

    if conflict_messages:
        return SyncPlan(
            manifest_path=path,
            pack_id=manifest.id,
            status="conflict",
            manifest=manifest,
            messages=(*tuple(conflict_messages), *tuple(stale_messages)),
        )

    if stale_messages:
        return SyncPlan(
            manifest_path=path,
            pack_id=manifest.id,
            status="stale-source",
            manifest=manifest,
            messages=tuple(stale_messages),
        )

    if sync_operations:
        return SyncPlan(
            manifest_path=path,
            pack_id=manifest.id,
            status="synced",
            manifest=manifest,
            operations=(
                *tuple(sync_operations),
                WriteOperation(
                    OperationKind.WRITE_MANIFEST,
                    target=path,
                    metadata={"pack_id": manifest.id},
                ),
            ),
            messages=tuple(
                f"clean source drift for {operation.metadata['skill_name']}"
                for operation in sync_operations
            ),
        )

    return SyncPlan(
        manifest_path=path,
        pack_id=manifest.id,
        status="ready",
        manifest=manifest,
        messages=(f"pack {manifest.id} is ready",),
    )


def apply_pack_sync(sync_plan: SyncPlan, apply: bool) -> ActivationResult:
    if not apply or sync_plan.status != "synced":
        return ActivationResult(
            status=sync_plan.status,
            pack_id=sync_plan.pack_id,
            manifest_path=sync_plan.manifest_path,
            messages=sync_plan.messages,
            operations=sync_plan.operations if not apply else (),
        )

    current_plan = plan_pack_sync(sync_plan.manifest_path)
    if current_plan.status != "synced":
        return ActivationResult(
            status=current_plan.status,
            pack_id=current_plan.pack_id,
            manifest_path=current_plan.manifest_path,
            messages=current_plan.messages,
            operations=(),
        )

    copied_skill_names = tuple(
        str(operation.metadata["skill_name"])
        for operation in current_plan.operations
        if operation.kind == OperationKind.COPY_SKILL
    )

    snapshots, snapshot_root = _snapshot_sync_targets(current_plan)
    try:
        for operation in _operations_of_kind(current_plan, OperationKind.COPY_SKILL):
            if operation.source is None or operation.target is None:
                raise ValueError("sync copy operation requires source and target")
            replace_skill_folder_atomic(operation.source, operation.target)

        updated_manifest = _with_synced_fingerprints(current_plan.manifest, copied_skill_names)
        save_pack_manifest(current_plan.manifest_path, updated_manifest)
    except Exception as error:
        rollback_message = ""
        try:
            _restore_snapshots(snapshots)
        except Exception as rollback_error:
            rollback_message = f"; rollback failed: {rollback_error}"
        return ActivationResult(
            status="failed",
            pack_id=current_plan.pack_id,
            manifest_path=current_plan.manifest_path,
            messages=(f"{error}{rollback_message}",),
            operations=(),
        )
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)

    return ActivationResult(
        status="synced",
        pack_id=current_plan.pack_id,
        manifest_path=current_plan.manifest_path,
        messages=current_plan.messages,
        operations=current_plan.operations,
    )


def _fingerprint_skill(path: Path) -> tuple[str | None, str | None]:
    try:
        validate_skill_folder(path)
    except ValueError as error:
        return None, str(error)
    return fingerprint_dir(path), None


def _validate_vault_path(manifest: PackManifest, skill: SkillEntry) -> str | None:
    if manifest.vault_root is None:
        return f"manifest vault root missing for {skill.name}"
    if _is_under(skill.vault_path, manifest.vault_root):
        return None
    return f"vault path for {skill.name} escapes manifest vault root: {skill.vault_path}"


def _is_under(path: Path, root: Path) -> bool:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    return resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root)


def _conflict_message(
    skill: SkillEntry,
    source_changed: bool,
    vault_error: str | None,
) -> str:
    if vault_error is not None:
        return f"vault missing or invalid for {skill.name}: {vault_error}"
    if source_changed:
        return f"source and vault both changed for {skill.name}"
    return f"vault changed for {skill.name}"


def _operations_of_kind(plan: SyncPlan, kind: OperationKind) -> tuple[WriteOperation, ...]:
    return tuple(operation for operation in plan.operations if operation.kind == kind)


@dataclass(frozen=True)
class _PathSnapshot:
    path: Path
    kind: str
    backup_path: Path | None = None


def _snapshot_sync_targets(plan: SyncPlan) -> tuple[tuple[_PathSnapshot, ...], Path]:
    snapshot_root = Path(tempfile.mkdtemp(prefix="sos-sync-rollback-"))
    targets = (
        *tuple(
            operation.target
            for operation in _operations_of_kind(plan, OperationKind.COPY_SKILL)
            if operation.target is not None
        ),
        plan.manifest_path,
    )
    snapshots = tuple(
        _snapshot_path(path, snapshot_root, index)
        for index, path in enumerate(_unique_paths(targets))
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
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def _with_synced_fingerprints(
    manifest: PackManifest,
    synced_skill_names: tuple[str, ...],
) -> PackManifest:
    names = frozenset(synced_skill_names)
    synced_at = datetime.now(timezone.utc).isoformat()
    return replace(
        manifest,
        skills=tuple(
            _synced_skill(skill, synced_at) if skill.name in names else skill
            for skill in manifest.skills
        ),
    )


def _synced_skill(skill: SkillEntry, synced_at: str) -> SkillEntry:
    return replace(
        skill,
        last_source_fingerprint=fingerprint_dir(skill.source_path),
        last_vault_fingerprint=fingerprint_dir(skill.vault_path),
        last_synced_at=synced_at,
    )
