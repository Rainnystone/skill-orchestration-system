from __future__ import annotations

from pathlib import Path

from sos.manifest import load_pack_manifest, load_registry
from sos.models import PackManifest
from sos.paths import RuntimePaths


def list_pack_manifests(runtime_paths: RuntimePaths) -> tuple[PackManifest, ...]:
    registry_path = runtime_paths.state / "registry.toml"
    if not registry_path.is_file():
        return ()
    return load_registry(registry_path).packs


def load_runtime_pack(runtime_paths: RuntimePaths, pack_id: str) -> PackManifest:
    safe_pack_id = _safe_component(pack_id, "pack")
    manifest_path = runtime_paths.packs / f"{safe_pack_id}.toml"
    if not manifest_path.is_file():
        raise ValueError(f"unknown pack: {pack_id}")
    return load_pack_manifest(manifest_path)


def filter_pack_skill(manifest: PackManifest, skill_name: str) -> PackManifest:
    matching_skills = tuple(skill for skill in manifest.skills if skill.name == skill_name)
    if not matching_skills:
        raise ValueError(f"unknown skill for pack {manifest.id}: {skill_name}")
    return PackManifest(
        id=manifest.id,
        display_name=manifest.display_name,
        pointer_skill=manifest.pointer_skill,
        skills=matching_skills,
        aliases=manifest.aliases,
        description=manifest.description,
        triggers=manifest.triggers,
        sync_policy=manifest.sync_policy,
        vault_root=manifest.vault_root,
    )


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
