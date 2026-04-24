from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from sos.models import PackManifest, Registry, SkillEntry
from sos.toml_io import read_toml, write_toml


def load_pack_manifest(path: str | Path) -> PackManifest:
    return _pack_manifest_from_dict(read_toml(path))


def save_pack_manifest(path: str | Path, manifest: PackManifest) -> None:
    write_toml(path, _pack_manifest_to_dict(manifest))


def load_registry(path: str | Path) -> Registry:
    data = read_toml(path)
    return Registry(
        packs=tuple(_pack_manifest_from_dict(pack) for pack in data.get("packs", ())),
        active_pointers=tuple(data.get("active_pointers", ())),
        aliases=dict(data.get("aliases", {})),
        backup_generations=tuple(data.get("backup_generations", ())),
        last_operation_ids=tuple(data.get("last_operation_ids", ())),
    )


def save_registry(path: str | Path, registry: Registry) -> None:
    write_toml(
        path,
        {
            "packs": [_pack_manifest_to_dict(pack) for pack in registry.packs],
            "active_pointers": list(registry.active_pointers),
            "aliases": dict(registry.aliases),
            "backup_generations": list(registry.backup_generations),
            "last_operation_ids": list(registry.last_operation_ids),
        },
    )


def validate_registry(registry: Registry) -> None:
    duplicate_aliases = _duplicates(alias for pack in registry.packs for alias in pack.aliases)
    duplicate_pointers = _duplicates(pack.pointer_skill for pack in registry.packs)
    if not duplicate_aliases and not duplicate_pointers:
        return

    problems: list[str] = []
    if duplicate_aliases:
        problems.append(f"duplicate aliases: {', '.join(duplicate_aliases)}")
    if duplicate_pointers:
        problems.append(f"duplicate pointer skills: {', '.join(duplicate_pointers)}")
    raise ValueError("; ".join(problems))


def update_registry_after_apply(
    registry: Registry,
    pack_manifests: Iterable[PackManifest],
    pointer_paths: Iterable[str | Path],
    backup_id: str,
) -> Registry:
    packs = tuple(pack_manifests)
    active_pointers = tuple(_pointer_name(pointer_path) for pointer_path in pointer_paths)
    aliases = {alias: pack.id for pack in packs for alias in pack.aliases}
    backup_generations = registry.backup_generations + ((backup_id,) if backup_id else ())
    return Registry(
        packs=packs,
        active_pointers=active_pointers,
        aliases=aliases,
        backup_generations=backup_generations,
        last_operation_ids=registry.last_operation_ids,
    )


def _pack_manifest_from_dict(data: dict[str, Any]) -> PackManifest:
    paths = data.get("paths", {})
    vault_root = paths.get("vault_root")
    return PackManifest(
        id=data["id"],
        display_name=data["display_name"],
        aliases=tuple(data.get("aliases", ())),
        description=data.get("description", ""),
        pointer_skill=data["pointer_skill"],
        sync_policy=data.get("sync_policy", "clean-auto"),
        vault_root=Path(vault_root) if vault_root else None,
        skills=tuple(_skill_entry_from_dict(skill) for skill in data.get("skills", ())),
        triggers=tuple(dict(trigger) for trigger in data.get("triggers", ())),
    )


def _pack_manifest_to_dict(manifest: PackManifest) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": manifest.id,
        "display_name": manifest.display_name,
        "aliases": list(manifest.aliases),
        "description": manifest.description,
        "pointer_skill": manifest.pointer_skill,
        "sync_policy": manifest.sync_policy,
    }
    if manifest.vault_root is not None:
        data["paths"] = {"vault_root": str(manifest.vault_root)}
    data["skills"] = [_skill_entry_to_dict(skill) for skill in manifest.skills]
    data["triggers"] = [dict(trigger) for trigger in manifest.triggers]
    return data


def _skill_entry_from_dict(data: dict[str, Any]) -> SkillEntry:
    return SkillEntry(
        name=data["name"],
        source_path=Path(data["source_path"]),
        vault_path=Path(data["vault_path"]),
        origin=data.get("origin", ""),
        enabled_before_apply=data.get("enabled_before_apply", True),
        last_source_fingerprint=data.get("last_source_fingerprint", ""),
        last_vault_fingerprint=data.get("last_vault_fingerprint", ""),
        last_synced_at=data.get("last_synced_at", ""),
    )


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


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    counts = Counter(values)
    return tuple(value for value, count in counts.items() if count > 1)


def _pointer_name(pointer_path: str | Path) -> str:
    pointer = Path(pointer_path)
    if pointer.name == "SKILL.md":
        return pointer.parent.name
    return pointer.name
