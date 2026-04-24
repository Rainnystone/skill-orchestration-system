from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def validate_skill_folder(path: str | Path) -> None:
    skill_path = Path(path)
    if not skill_path.is_dir():
        raise ValueError(f"Skill folder is not a directory: {skill_path}")
    if not (skill_path / "SKILL.md").is_file():
        raise ValueError(f"Missing SKILL.md in skill folder: {skill_path}")


def copy_skill_folder(source: str | Path, target: str | Path) -> None:
    source_path = Path(source)
    target_path = Path(target)
    validate_skill_folder(source_path)
    shutil.copytree(source_path, target_path)


def replace_skill_folder_atomic(source: str | Path, target: str | Path) -> None:
    source_path = Path(source)
    target_path = Path(target)
    validate_skill_folder(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = _reserved_sibling_temp_path(target_path, suffix=".tmp")
    backup_path: Path | None = None

    try:
        shutil.copytree(source_path, temp_path)
        validate_skill_folder(temp_path)
        if target_path.exists():
            backup_path = _reserved_sibling_temp_path(target_path, suffix=".bak")
            os.replace(target_path, backup_path)
        os.replace(temp_path, target_path)
        if backup_path is not None:
            shutil.rmtree(backup_path)
            backup_path = None
    except Exception:
        if backup_path is not None and backup_path.exists() and not target_path.exists():
            os.replace(backup_path, target_path)
            backup_path = None
        raise
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)
        if backup_path is not None and backup_path.exists() and target_path.exists():
            shutil.rmtree(backup_path)


def _reserved_sibling_temp_path(target_path: Path, suffix: str) -> Path:
    temp_path = Path(
        tempfile.mkdtemp(
            prefix=f".{target_path.name}.",
            suffix=suffix,
            dir=target_path.parent,
        )
    )
    temp_path.rmdir()
    return temp_path
