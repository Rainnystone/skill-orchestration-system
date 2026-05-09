from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from pathlib import Path

from sos.codex_config import load_codex_config
from sos.fingerprint import fingerprint_dir
from sos.manifest import load_registry
from sos.models import Registry, SkillEntry
from sos.paths import RuntimePaths
from sos.scanner import scan_skill_roots


@dataclass(frozen=True)
class ChangeReport:
    new_unmanaged: tuple[Path, ...] = ()
    source_missing: tuple[SkillEntry, ...] = ()
    source_changed: tuple[SkillEntry, ...] = ()
    vault_changed: tuple[SkillEntry, ...] = ()
    pointer_missing: tuple[Path, ...] = ()
    managed_source_enabled: tuple[SkillEntry, ...] = ()


def detect_changes(
    skill_root: str | Path,
    runtime_paths: RuntimePaths,
    codex_config_path: str | Path | None,
) -> ChangeReport:
    root = Path(skill_root)
    disabled_paths = _disabled_paths(codex_config_path)
    registry = _load_registry(runtime_paths)
    managed_skills = tuple(skill for pack in registry.packs for skill in pack.skills)
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
        skill for skill in managed_skills if not skill.source_path.exists()
    )
    source_changed = _sort_skills(
        skill
        for skill in managed_skills
        if skill.last_source_fingerprint
        and skill.source_path.exists()
        and fingerprint_dir(skill.source_path) != skill.last_source_fingerprint
    )
    vault_changed = _sort_skills(
        skill
        for skill in managed_skills
        if skill.last_vault_fingerprint
        and (
            not skill.vault_path.exists()
            or fingerprint_dir(skill.vault_path) != skill.last_vault_fingerprint
        )
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
