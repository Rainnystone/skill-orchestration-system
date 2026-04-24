from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Iterable

from sos.models import PackManifest, Registry
from sos.toml_io import atomic_write_text

_TEMPLATE_ROOT: Path | None = None
_DEFAULT_RUNTIME_ROOT = Path("~/.sos")
_PLACEHOLDER_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")


def render_pack_pointer(target: str | Path, manifest: PackManifest) -> None:
    pointer_skill = _safe_pointer_skill_name(manifest.pointer_skill)
    manifest_path = _manifest_path(manifest)
    vault_root = manifest.vault_root or _DEFAULT_RUNTIME_ROOT / "vault" / manifest.id
    activation_command = f"sos pack activate {manifest.id} --sync={manifest.sync_policy}"
    description = _compact_description(manifest)
    text = _render_template(
        "pointer-skill.md.tmpl",
        {
            "name": pointer_skill,
            "description": description,
            "display_name": manifest.display_name,
            "pack_id": manifest.id,
            "manifest_path": str(manifest_path),
            "vault_root": str(vault_root),
            "activation_command": activation_command,
        },
    )
    atomic_write_text(_skill_file_path(target, pointer_skill), text)


def render_companion_skill(target: str | Path, registry_path: str | Path) -> None:
    text = _render_template(
        "companion-skill.md.tmpl",
        {"registry_path": str(registry_path)},
    )
    atomic_write_text(_skill_file_path(target, "sos-haruhi"), text)


def render_v1_active_skills(
    active_root: str | Path,
    registry: Registry,
    manifests: Iterable[PackManifest],
) -> tuple[Path, ...]:
    root = Path(active_root)
    ordered_manifests = _ordered_manifests(registry, tuple(manifests))
    for manifest in ordered_manifests:
        _safe_pointer_skill_name(manifest.pointer_skill)
    registry_path = _registry_path(ordered_manifests)
    written: list[Path] = []

    companion_target = root / "sos-haruhi" / "SKILL.md"
    render_companion_skill(companion_target, registry_path)
    written.append(companion_target)

    for manifest in ordered_manifests:
        pointer_target = root / manifest.pointer_skill / "SKILL.md"
        render_pack_pointer(pointer_target, manifest)
        written.append(pointer_target)

    return tuple(written)


def _render_template(template_name: str, values: dict[str, str]) -> str:
    text = _read_template(template_name)
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    unresolved = tuple(
        sorted({match.group(1).strip() for match in _PLACEHOLDER_RE.finditer(text)})
    )
    if unresolved:
        raise ValueError(f"unresolved template placeholders: {', '.join(unresolved)}")
    return text


def _read_template(template_name: str) -> str:
    if _TEMPLATE_ROOT is not None:
        return (_TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")

    template = resources.files("sos").joinpath("templates", template_name)
    return template.read_text(encoding="utf-8")


def _skill_file_path(target: str | Path, skill_name: str) -> Path:
    safe_skill_name = _safe_pointer_skill_name(skill_name)
    path = Path(target)
    if path.name == "SKILL.md":
        return path
    if path.name == safe_skill_name:
        return path / "SKILL.md"
    return path / safe_skill_name / "SKILL.md"


def _safe_pointer_skill_name(name: str) -> str:
    if (
        not name.startswith("sos-")
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).is_absolute()
        or Path(name).name != name
    ):
        raise ValueError(f"unsafe pointer skill name: {name}")
    return name


def _compact_description(manifest: PackManifest) -> str:
    base = manifest.description or f"Activate the {manifest.display_name} SOS pack."
    compact = " ".join(base.split())
    return _yaml_quoted(compact[:180])


def _yaml_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _ordered_manifests(
    registry: Registry,
    manifests: tuple[PackManifest, ...],
) -> tuple[PackManifest, ...]:
    by_id = {manifest.id: manifest for manifest in manifests}
    if registry.packs:
        missing_ids = tuple(pack.id for pack in registry.packs if pack.id not in by_id)
        if missing_ids:
            raise ValueError(f"registry references missing manifests: {', '.join(missing_ids)}")
        return tuple(by_id[pack.id] for pack in registry.packs)
    return manifests


def _manifest_path(manifest: PackManifest) -> Path:
    runtime_root = _runtime_root_from_manifest(manifest)
    return runtime_root / "packs" / f"{manifest.id}.toml"


def _registry_path(manifests: tuple[PackManifest, ...]) -> Path:
    if not manifests:
        return _DEFAULT_RUNTIME_ROOT / "state" / "registry.toml"
    return _runtime_root_from_manifest(manifests[0]) / "state" / "registry.toml"


def _runtime_root_from_manifest(manifest: PackManifest) -> Path:
    if manifest.vault_root is None:
        return _DEFAULT_RUNTIME_ROOT

    vault_root = Path(manifest.vault_root)
    # Runtime layout is <root>/vault/<pack>, so manifests live at <root>/packs/<pack>.toml.
    if vault_root.parent.name == "vault":
        return vault_root.parent.parent
    return vault_root.parent
