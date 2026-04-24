from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

import tomli_w

from sos.toml_io import atomic_write_text, read_toml


def load_codex_config(path: str | Path) -> dict[str, Any]:
    return read_toml(path)


def plan_disable_skill_paths(
    config: dict[str, Any],
    skill_md_paths: Iterable[str | Path],
) -> dict[str, Any]:
    planned = copy.deepcopy(config)
    skills = planned.setdefault("skills", {})
    if not isinstance(skills, dict):
        raise ValueError("Codex config skills must be a TOML table")

    entries = skills.get("config", [])
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ValueError("Codex config skills.config must be a list")

    next_entries = list(entries)
    _validate_config_entries(next_entries)
    for skill_path in _unique_path_strings(skill_md_paths):
        matched_existing = False
        for index, entry in enumerate(next_entries):
            if entry.get("path") == skill_path:
                next_entries[index] = {**entry, "enabled": False}
                matched_existing = True
        if not matched_existing:
            next_entries.append({"path": skill_path, "enabled": False})

    skills["config"] = next_entries
    return planned


def write_codex_config_atomic(
    config_path: str | Path,
    next_config: dict[str, Any],
    backup_path: str | Path,
) -> None:
    target = Path(config_path)
    backup = Path(backup_path)
    original_existed = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_existed else ""

    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_text(original_text, encoding="utf-8")

    try:
        atomic_write_text(target, tomli_w.dumps(next_config))
        read_toml(target)
    except Exception:
        _restore_original_text(target, original_text, original_existed)
        raise


def disable_skill_paths_with_backup(
    config_path: str | Path,
    skill_md_paths: Iterable[str | Path],
    backup_path: str | Path | None,
    apply: bool,
) -> dict[str, Any]:
    current_config = load_codex_config(config_path)
    planned_config = plan_disable_skill_paths(current_config, skill_md_paths)

    if not apply:
        return planned_config
    if backup_path is None:
        raise ValueError("backup_path is required when applying Codex config changes")

    write_codex_config_atomic(config_path, planned_config, backup_path)
    return planned_config


def _validate_config_entries(entries: list[Any]) -> None:
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Codex config skills.config entries must be tables")


def _unique_path_strings(skill_md_paths: Iterable[str | Path]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for skill_path in skill_md_paths:
        path_string = str(skill_path)
        if path_string not in seen:
            unique.append(path_string)
            seen.add(path_string)
    return tuple(unique)


def _restore_original_text(target: Path, original_text: str, original_existed: bool) -> None:
    if not original_existed:
        if target.exists():
            target.unlink()
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.rollback.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(original_text)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
