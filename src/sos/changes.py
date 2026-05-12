from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

from sos.codex_config import load_codex_config
from sos.fingerprint import fingerprint_dir
from sos.manifest import load_pack_manifest, load_registry
from sos.models import PackManifest, Registry, SkillEntry
from sos.paths import RuntimePaths
from sos.pointer import render_companion_skill, render_pack_pointer
from sos.scanner import scan_skill_roots


@dataclass(frozen=True)
class ChangeReport:
    new_unmanaged: tuple[Path, ...] = ()
    source_missing: tuple[SkillEntry, ...] = ()
    source_changed: tuple[SkillEntry, ...] = ()
    vault_changed: tuple[SkillEntry, ...] = ()
    pointer_missing: tuple[Path, ...] = ()
    pointer_stale: tuple[Path, ...] = ()
    managed_source_enabled: tuple[SkillEntry, ...] = ()


def detect_changes(
    skill_root: str | Path,
    runtime_paths: RuntimePaths,
    codex_config_path: str | Path | None,
) -> ChangeReport:
    root = Path(skill_root)
    disabled_paths = _disabled_paths(codex_config_path)
    registry = _load_registry(runtime_paths)
    current_manifests = _load_current_manifests(runtime_paths, registry)
    managed_skills = tuple(skill for pack in current_manifests for skill in pack.skills)
    managed_sources = frozenset(_comparable_path(skill.source_path) for skill in managed_skills)
    active_pointers = frozenset(registry.active_pointers)
    scanned_skills = scan_skill_roots((root,), disabled_paths=disabled_paths)

    new_unmanaged = tuple(
        sorted(
            (
                skill.folder
                for skill in scanned_skills
                if _comparable_path(skill.folder) not in managed_sources
                and skill.name not in active_pointers
                and skill.folder.name not in active_pointers
                and not skill.name.startswith("sos-")
                and not skill.folder.name.startswith("sos-")
            ),
            key=lambda path: path.as_posix(),
        )
    )
    source_missing = _sort_skills(
        skill for skill in managed_skills if _source_missing(skill)
    )
    source_changed = _sort_skills(
        skill
        for skill in managed_skills
        if not _source_missing(skill) and _source_changed(skill)
    )
    vault_changed = _sort_skills(
        skill
        for skill in managed_skills
        if _vault_changed(skill)
    )
    pointer_missing = tuple(
        sorted(
            (
                root / pointer / "SKILL.md"
                for pointer in active_pointers
                if not (root / pointer / "SKILL.md").is_file()
            ),
            key=lambda path: path.as_posix(),
        )
    )
    pointer_stale = _detect_stale_pointers(
        root,
        runtime_paths,
        current_manifests,
        active_pointers,
    )
    managed_source_enabled = _sort_skills(
        skill
        for skill in managed_skills
        if (skill.source_path / "SKILL.md").is_file()
        and _comparable_path(skill.source_path / "SKILL.md") not in disabled_paths
    )
    return ChangeReport(
        new_unmanaged=new_unmanaged,
        source_missing=source_missing,
        source_changed=source_changed,
        vault_changed=vault_changed,
        pointer_missing=pointer_missing,
        pointer_stale=pointer_stale,
        managed_source_enabled=managed_source_enabled,
    )


def _disabled_paths(codex_config_path: str | Path | None) -> frozenset[Path]:
    if codex_config_path is None:
        return frozenset()
    path = Path(codex_config_path)
    if not path.exists():
        return frozenset()
    try:
        config = load_codex_config(path)
    except Exception:
        return frozenset()
    skills = config.get("skills", {})
    if not isinstance(skills, dict):
        return frozenset()
    entries = skills.get("config", ())
    if not isinstance(entries, list):
        return frozenset()
    return frozenset(
        _comparable_path(Path(str(entry["path"])))
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("enabled") is False
        and "path" in entry
    )


def _load_registry(runtime_paths: RuntimePaths) -> Registry:
    registry_path = runtime_paths.state / "registry.toml"
    if not registry_path.is_file():
        return Registry()
    return load_registry(registry_path)


def _load_current_manifests(
    runtime_paths: RuntimePaths,
    registry: Registry,
) -> tuple[PackManifest, ...]:
    manifests: list[PackManifest] = []
    seen_pack_ids: set[str] = set()

    for registry_manifest in registry.packs:
        manifest_path = runtime_paths.packs / f"{registry_manifest.id}.toml"
        if manifest_path.is_file():
            manifests.append(load_pack_manifest(manifest_path))
        else:
            manifests.append(registry_manifest)
        seen_pack_ids.add(registry_manifest.id)

    if runtime_paths.packs.is_dir():
        for manifest_path in sorted(runtime_paths.packs.glob("*.toml")):
            if manifest_path.stem in seen_pack_ids:
                continue
            manifests.append(load_pack_manifest(manifest_path))

    return tuple(manifests)


def _effective_source_path(skill: SkillEntry) -> Path:
    if skill.archived_source_path is not None:
        return skill.archived_source_path
    return skill.source_path


def _source_missing(skill: SkillEntry) -> bool:
    return not _effective_source_path(skill).exists()


def _source_changed(skill: SkillEntry) -> bool:
    effective = _effective_source_path(skill)
    source_fingerprint = _existing_fingerprint(effective)
    if source_fingerprint is None:
        return False
    if skill.last_source_fingerprint:
        return source_fingerprint != skill.last_source_fingerprint

    vault_fingerprint = _existing_fingerprint(skill.vault_path)
    return vault_fingerprint is not None and source_fingerprint != vault_fingerprint


def _vault_changed(skill: SkillEntry) -> bool:
    vault_fingerprint = _existing_fingerprint(skill.vault_path)
    if vault_fingerprint is None:
        return True
    if skill.last_vault_fingerprint:
        return vault_fingerprint != skill.last_vault_fingerprint

    source_fingerprint = _existing_fingerprint(skill.source_path)
    return source_fingerprint is not None and vault_fingerprint != source_fingerprint


def _existing_fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    return fingerprint_dir(path)


def _sort_skills(skills: Iterable[SkillEntry]) -> tuple[SkillEntry, ...]:
    return tuple(
        sorted(
            tuple(skills),
            key=lambda skill: (
                skill.name,
                skill.source_path.as_posix(),
                skill.vault_path.as_posix(),
            ),
        )
    )


def _comparable_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _detect_stale_pointers(
    root: Path,
    runtime_paths: RuntimePaths,
    manifests: tuple[PackManifest, ...],
    active_pointers: frozenset[str],
) -> tuple[Path, ...]:
    stale_paths: list[Path] = []
    registry_path = runtime_paths.state / "registry.toml"
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for manifest in manifests:
            pointer_name = manifest.pointer_skill
            actual_path = root / pointer_name / "SKILL.md"
            if pointer_name not in active_pointers or not actual_path.is_file():
                continue
            expected_path = temp_root / pointer_name / "SKILL.md"
            render_pack_pointer(expected_path, manifest)
            if actual_path.read_text(encoding="utf-8") != expected_path.read_text(
                encoding="utf-8"
            ):
                stale_paths.append(actual_path)

        companion_path = root / "sos-haruhi" / "SKILL.md"
        if "sos-haruhi" in active_pointers and companion_path.is_file():
            expected_companion = temp_root / "sos-haruhi" / "SKILL.md"
            render_companion_skill(expected_companion, registry_path)
            if companion_path.read_text(encoding="utf-8") != expected_companion.read_text(
                encoding="utf-8"
            ):
                stale_paths.append(companion_path)

    return tuple(sorted(stale_paths, key=lambda path: path.as_posix()))
