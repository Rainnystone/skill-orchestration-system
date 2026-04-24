from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ScannedSkill:
    name: str
    description: str
    folder: Path
    skill_md: Path


def scan_skill_roots(
    roots: Iterable[Path], disabled_paths: Iterable[Path] = ()
) -> tuple[ScannedSkill, ...]:
    disabled = frozenset(_comparable_path(path) for path in disabled_paths)
    skill_paths = tuple(
        sorted(
            (
                skill_md
                for root in roots
                for skill_md in Path(root).glob("*/SKILL.md")
                if _comparable_path(skill_md) not in disabled
            ),
            key=lambda path: path.as_posix(),
        )
    )

    return tuple(_scan_skill(skill_md) for skill_md in skill_paths)


def _scan_skill(skill_md: Path) -> ScannedSkill:
    frontmatter = _read_frontmatter(skill_md)
    fallback_name = skill_md.parent.name
    return ScannedSkill(
        name=frontmatter.get("name", fallback_name),
        description=frontmatter.get("description", ""),
        folder=skill_md.parent,
        skill_md=skill_md,
    )


def _read_frontmatter(skill_md: Path) -> dict[str, str]:
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def _comparable_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path

