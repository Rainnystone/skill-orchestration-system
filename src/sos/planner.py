from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from sos.models import (
    OperationKind,
    PackManifest,
    Registry,
    SkillEntry,
    WriteOperation,
    WritePlan,
)
from sos.paths import RuntimePaths
from sos.propose import PackProposal
from sos.skill_fs import validate_skill_folder
from sos.toml_io import read_toml, write_toml


def build_pack_apply_plan(
    runtime_paths: RuntimePaths,
    active_skill_root: str | Path,
    codex_config_path: str | Path,
    proposals: Iterable[PackProposal],
) -> WritePlan:
    proposal_tuple = tuple(proposals)
    _validate_proposals(proposal_tuple)
    active_root = Path(active_skill_root)
    config_path = Path(codex_config_path)
    plan_id = _plan_id(runtime_paths, active_root, config_path, proposal_tuple)
    manifests = _pack_manifests(runtime_paths, active_root, proposal_tuple)
    registry = _registry(manifests)

    operations = (
        _backup_config_operation(runtime_paths, plan_id, config_path),
        _backup_vault_operation(runtime_paths, plan_id),
        *_copy_operations(manifests),
        *_manifest_operations(runtime_paths, manifests),
        _registry_operation(runtime_paths, registry),
        *_pointer_operations(active_root, manifests),
        *_disable_config_operations(config_path, manifests),
        *_delete_source_candidate_operations(active_root, manifests),
    )
    return WritePlan(
        plan_id=plan_id,
        pack_ids=tuple(manifest.id for manifest in manifests),
        operations=operations,
        requires_apply=True,
        delete_source_requested=False,
        second_confirmation=False,
    )


def serialize_write_plan(plan: WritePlan, path: str | Path) -> None:
    write_toml(path, _write_plan_to_dict(plan))


def load_write_plan(path: str | Path) -> WritePlan:
    data = read_toml(path)
    return WritePlan(
        plan_id=data["plan_id"],
        pack_ids=tuple(data.get("pack_ids", ())),
        operations=tuple(
            _write_operation_from_dict(operation)
            for operation in data.get("operations", ())
        ),
        requires_apply=data.get("requires_apply", False),
        delete_source_requested=data.get("delete_source_requested", False),
        second_confirmation=data.get("second_confirmation", False),
    )


def summarize_write_plan(plan: WritePlan) -> str:
    lines = [
        f"plan_id: {plan.plan_id}",
        f"pack_ids: {', '.join(plan.pack_ids)}",
        f"requires_apply: {str(plan.requires_apply).lower()}",
        f"delete_source_requested: {str(plan.delete_source_requested).lower()}",
        f"second_confirmation: {str(plan.second_confirmation).lower()}",
        "operations:",
    ]
    for operation in plan.operations:
        target = operation.target if operation.target is not None else operation.source
        lines.append(f"- {operation.kind.value}: {target}")

    delete_candidates = tuple(
        operation
        for operation in plan.operations
        if operation.kind == OperationKind.DELETE_SOURCE
        and operation.metadata.get("candidate") is True
    )
    if delete_candidates:
        lines.append("source deletion candidates (candidate only):")
        for operation in delete_candidates:
            target = operation.target if operation.target is not None else operation.source
            lines.append(f"- {target} (candidate only)")

    return "\n".join(lines)


def _plan_id(
    runtime_paths: RuntimePaths,
    active_root: Path,
    config_path: Path,
    proposals: tuple[PackProposal, ...],
) -> str:
    seed = {
        "version": 1,
        "runtime_root": str(runtime_paths.root),
        "active_skill_root": str(active_root),
        "codex_config_path": str(config_path),
        "proposals": [
            {
                "pack_id": proposal.pack_id,
                "skill_names": list(proposal.skill_names),
                "reason": proposal.reason,
            }
            for proposal in proposals
        ],
    }
    encoded = json.dumps(seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    return f"plan-{digest}"


def _pack_manifests(
    runtime_paths: RuntimePaths,
    active_root: Path,
    proposals: tuple[PackProposal, ...],
) -> tuple[PackManifest, ...]:
    manifests: list[PackManifest] = []
    for proposal in proposals:
        skills = tuple(
            _skill_entry(runtime_paths, active_root, proposal.pack_id, skill_name)
            for skill_name in proposal.skill_names
        )
        manifests.append(
            PackManifest(
                id=proposal.pack_id,
                display_name=_display_name(proposal.pack_id),
                pointer_skill=_pointer_skill(proposal.pack_id),
                skills=skills,
                aliases=_aliases(proposal.pack_id),
                description=proposal.reason,
                triggers=tuple(
                    {"term": skill.name, "reason": proposal.reason}
                    for skill in skills
                ),
                sync_policy="clean-auto",
                vault_root=runtime_paths.vault / proposal.pack_id,
            )
        )
    return tuple(manifests)


def _skill_entry(
    runtime_paths: RuntimePaths,
    active_root: Path,
    pack_id: str,
    skill_name: str,
) -> SkillEntry:
    source_path = active_root / skill_name
    _ensure_under(source_path, active_root, "source skill path")
    validate_skill_folder(source_path)
    vault_path = runtime_paths.vault / pack_id / skill_name
    _ensure_under(vault_path, runtime_paths.vault, "vault target path")
    return SkillEntry(
        name=skill_name,
        source_path=source_path,
        vault_path=vault_path,
        origin="codex",
        enabled_before_apply=True,
    )


def _registry(manifests: tuple[PackManifest, ...]) -> Registry:
    return Registry(
        packs=manifests,
        active_pointers=("sos-haruhi",)
        + tuple(manifest.pointer_skill for manifest in manifests),
        aliases={alias: manifest.id for manifest in manifests for alias in manifest.aliases},
    )


def _backup_config_operation(
    runtime_paths: RuntimePaths,
    plan_id: str,
    config_path: Path,
) -> WriteOperation:
    backup_target = runtime_paths.backups / plan_id / "config.toml"
    _ensure_under(backup_target, runtime_paths.backups, "config backup target path")
    return WriteOperation(
        OperationKind.BACKUP_CODEX_CONFIG,
        source=config_path,
        target=backup_target,
        metadata={
            "backup_id": plan_id,
            "codex_config_path": str(config_path),
            "reason": "pack apply",
        },
    )


def _backup_vault_operation(runtime_paths: RuntimePaths, plan_id: str) -> WriteOperation:
    backup_target = runtime_paths.backups / plan_id / "vault"
    _ensure_under(backup_target, runtime_paths.backups, "vault backup target path")
    return WriteOperation(
        OperationKind.BACKUP_VAULT,
        source=runtime_paths.vault,
        target=backup_target,
        metadata={
            "backup_id": plan_id,
            "vault_root": str(runtime_paths.vault),
            "reason": "pack apply",
        },
    )


def _copy_operations(manifests: tuple[PackManifest, ...]) -> tuple[WriteOperation, ...]:
    return tuple(
        WriteOperation(
            OperationKind.COPY_SKILL,
            source=skill.source_path,
            target=skill.vault_path,
            metadata={"pack_id": manifest.id, "skill_name": skill.name},
        )
        for manifest in manifests
        for skill in manifest.skills
    )


def _manifest_operations(
    runtime_paths: RuntimePaths,
    manifests: tuple[PackManifest, ...],
) -> tuple[WriteOperation, ...]:
    return tuple(
        _manifest_operation(runtime_paths, manifest)
        for manifest in manifests
    )


def _manifest_operation(
    runtime_paths: RuntimePaths,
    manifest: PackManifest,
) -> WriteOperation:
    target = runtime_paths.packs / f"{manifest.id}.toml"
    _ensure_under(target, runtime_paths.packs, "manifest target path")
    return WriteOperation(
        OperationKind.WRITE_MANIFEST,
        target=target,
        metadata={
            "pack_id": manifest.id,
            "manifest": _pack_manifest_to_dict(manifest),
        },
    )


def _registry_operation(runtime_paths: RuntimePaths, registry: Registry) -> WriteOperation:
    target = runtime_paths.state / "registry.toml"
    _ensure_under(target, runtime_paths.state, "registry target path")
    return WriteOperation(
        OperationKind.WRITE_REGISTRY,
        target=target,
        metadata={"registry": _registry_to_dict(registry)},
    )


def _pointer_operations(
    active_root: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[WriteOperation, ...]:
    companion_target = active_root / "sos-haruhi" / "SKILL.md"
    _ensure_under(companion_target, active_root, "companion pointer target path")
    companion = WriteOperation(
        OperationKind.WRITE_POINTER,
        target=companion_target,
        metadata={"pointer_skill": "sos-haruhi", "role": "companion"},
    )
    pack_pointers = tuple(
        _pack_pointer_operation(active_root, manifest)
        for manifest in manifests
    )
    return (companion, *pack_pointers)


def _pack_pointer_operation(active_root: Path, manifest: PackManifest) -> WriteOperation:
    target = active_root / manifest.pointer_skill / "SKILL.md"
    _ensure_under(target, active_root, "pack pointer target path")
    return WriteOperation(
        OperationKind.WRITE_POINTER,
        target=target,
        metadata={
            "pointer_skill": manifest.pointer_skill,
            "role": "pack",
            "pack_id": manifest.id,
        },
    )


def _disable_config_operations(
    config_path: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[WriteOperation, ...]:
    return tuple(
        WriteOperation(
            OperationKind.DISABLE_CODEX_SKILL,
            source=skill.source_path / "SKILL.md",
            target=config_path,
            metadata={
                "pack_id": manifest.id,
                "skill_name": skill.name,
                "skill_md_path": str(skill.source_path / "SKILL.md"),
            },
        )
        for manifest in manifests
        for skill in manifest.skills
    )


def _delete_source_candidate_operations(
    active_root: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[WriteOperation, ...]:
    return tuple(
        _delete_source_candidate_operation(active_root, manifest, skill)
        for manifest in manifests
        for skill in manifest.skills
    )


def _delete_source_candidate_operation(
    active_root: Path,
    manifest: PackManifest,
    skill: SkillEntry,
) -> WriteOperation:
    _ensure_under(skill.source_path, active_root, "delete source target path")
    return WriteOperation(
        OperationKind.DELETE_SOURCE,
        target=skill.source_path,
        metadata={
            "pack_id": manifest.id,
            "skill_name": skill.name,
            "candidate": True,
            "active": False,
        },
    )


def _write_plan_to_dict(plan: WritePlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "pack_ids": list(plan.pack_ids),
        "requires_apply": plan.requires_apply,
        "delete_source_requested": plan.delete_source_requested,
        "second_confirmation": plan.second_confirmation,
        "operations": [_write_operation_to_dict(operation) for operation in plan.operations],
    }


def _write_operation_to_dict(operation: WriteOperation) -> dict[str, Any]:
    data: dict[str, Any] = {"kind": operation.kind.value}
    if operation.source is not None:
        data["source"] = str(operation.source)
    if operation.target is not None:
        data["target"] = str(operation.target)
    if operation.metadata:
        data["metadata"] = _metadata_to_plain_dict(operation.metadata)
    return data


def _write_operation_from_dict(data: dict[str, Any]) -> WriteOperation:
    source = Path(data["source"]) if "source" in data else None
    target = Path(data["target"]) if "target" in data else None
    return WriteOperation(
        OperationKind(data["kind"]),
        source=source,
        target=target,
        metadata=dict(data.get("metadata", {})),
    )


def _metadata_to_plain_dict(metadata: Any) -> Any:
    if isinstance(metadata, Mapping):
        return {key: _metadata_to_plain_dict(value) for key, value in metadata.items()}
    if isinstance(metadata, tuple):
        return [_metadata_to_plain_dict(value) for value in metadata]
    if isinstance(metadata, list):
        return [_metadata_to_plain_dict(value) for value in metadata]
    if isinstance(metadata, Path):
        return str(metadata)
    return metadata


def _pack_manifest_to_dict(manifest: PackManifest) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": manifest.id,
        "display_name": manifest.display_name,
        "aliases": list(manifest.aliases),
        "description": manifest.description,
        "pointer_skill": manifest.pointer_skill,
        "sync_policy": manifest.sync_policy,
        "skills": [_skill_entry_to_dict(skill) for skill in manifest.skills],
        "triggers": [dict(trigger) for trigger in manifest.triggers],
    }
    if manifest.vault_root is not None:
        data["paths"] = {"vault_root": str(manifest.vault_root)}
    return data


def _skill_entry_to_dict(skill: SkillEntry) -> dict[str, Any]:
    return {
        "name": skill.name,
        "source_path": str(skill.source_path),
        "vault_path": str(skill.vault_path),
        "origin": skill.origin,
        "enabled_before_apply": skill.enabled_before_apply,
        "last_source_fingerprint": skill.last_source_fingerprint,
        "last_vault_fingerprint": skill.last_vault_fingerprint,
        "last_synced_at": skill.last_synced_at,
    }


def _registry_to_dict(registry: Registry) -> dict[str, Any]:
    return {
        "packs": [_pack_manifest_to_dict(pack) for pack in registry.packs],
        "active_pointers": list(registry.active_pointers),
        "aliases": dict(registry.aliases),
        "backup_generations": list(registry.backup_generations),
        "last_operation_ids": list(registry.last_operation_ids),
    }


def _display_name(pack_id: str) -> str:
    return pack_id.replace("-", " ").title()


def _pointer_skill(pack_id: str) -> str:
    pointer_skill = f"sos-{pack_id}"
    _safe_component(pointer_skill, "pointer_skill")
    if not pointer_skill.startswith("sos-"):
        raise ValueError(f"unsafe pointer_skill: {pointer_skill}")
    return pointer_skill


def _aliases(pack_id: str) -> tuple[str, ...]:
    if pack_id == "game-design":
        return ("game",)
    return (pack_id,)


def _validate_proposals(proposals: tuple[PackProposal, ...]) -> None:
    for proposal in proposals:
        _safe_component(proposal.pack_id, "pack_id")
        _pointer_skill(proposal.pack_id)
        for skill_name in proposal.skill_names:
            _safe_component(skill_name, "skill_name")


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


def _ensure_under(path: Path, root: Path, label: str) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root):
        return
    raise ValueError(f"{label} escapes expected root: {path}")
