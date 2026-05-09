from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Collection, Iterable

from sos.scanner import ScannedSkill


@dataclass(frozen=True)
class PackProposal:
    pack_id: str
    skill_names: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_names", tuple(self.skill_names))


GAME_STUDIO_FAMILY_NAMES = frozenset(
    (
        "develop-web-game",
        "game-playtest",
        "game-studio",
        "game-ui-frontend",
        "phaser-2d-game",
        "react-three-fiber-game",
        "sprite-pipeline",
        "three-webgl-game",
        "web-3d-asset-pipeline",
        "web-game-foundations",
    )
)

SOURCE_FAMILIES = (
    (
        "apify",
        ("apify",),
        "Shared source/tool family signal: Apify in skill name or description.",
    ),
    (
        "obsidian",
        ("obsidian", "json canvas", "json-canvas"),
        "Shared source/tool family signal: Obsidian or Canvas in skill name or description.",
    ),
    (
        "game-design",
        ("game", "gameplay", "phaser", "three", "webgl", "sprite"),
        "Shared source/tool family signal: game design in skill name or description.",
    ),
)

FUNCTIONAL_GROUPS = (
    (
        "docs",
        (
            "document",
            "documents",
            "markdown",
            "docx",
            "report",
            "writing",
            "publishing",
            "documentation",
        ),
        "Shared functional signal: document or writing terms in skill name or description.",
    ),
    (
        "browser",
        (
            "browser",
            "playwright",
            "screenshot",
            "page inspection",
            "web automation",
        ),
        "Shared functional signal: browser automation terms in skill name or description.",
    ),
    (
        "deploy",
        ("deployment", "deploy", "hosting", "render", "vercel", "docker", "publish"),
        "Shared functional signal: deployment or hosting terms in skill name or description.",
    ),
    (
        "data",
        ("csv", "json", "sql", "dataset", "analytics", "extraction", "transform"),
        "Shared functional signal: data workflow terms in skill name or description.",
    ),
)


def propose_builtin_packs(skills: Iterable[ScannedSkill]) -> tuple[PackProposal, ...]:
    remaining = list(sorted(skills, key=lambda skill: skill.name))
    proposals: list[PackProposal] = []

    for pack_id, keywords, reason in SOURCE_FAMILIES:
        exact_names = GAME_STUDIO_FAMILY_NAMES if pack_id == "game-design" else ()
        matches = _matching_skills(remaining, keywords, exact_names=exact_names)
        if matches:
            proposals.extend(
                _proposals(pack_id, tuple(skill.name for skill in matches), reason)
            )
            matched_names = {skill.name for skill in matches}
            remaining = [skill for skill in remaining if skill.name not in matched_names]

    for pack_id, keywords, reason in FUNCTIONAL_GROUPS:
        matches = _matching_skills(remaining, keywords)
        if matches:
            proposals.extend(
                _proposals(pack_id, tuple(skill.name for skill in matches), reason)
            )
            matched_names = {skill.name for skill in matches}
            remaining = [skill for skill in remaining if skill.name not in matched_names]

    return tuple(proposals)


def _proposals(
    pack_id: str, skill_names: tuple[str, ...], base_reason: str
) -> tuple[PackProposal, ...]:
    if not skill_names:
        return ()

    if len(skill_names) > 20:
        return _family_proposals(pack_id, skill_names, base_reason)

    return (PackProposal(pack_id=pack_id, skill_names=skill_names, reason=base_reason),)


def _family_proposals(
    pack_id: str, skill_names: tuple[str, ...], base_reason: str
) -> tuple[PackProposal, ...]:
    reason = (
        f"{base_reason} More than 20 matching skills; split by skill/tool family "
        "into stable semantic proposals."
    )
    return tuple(
        PackProposal(
            pack_id=f"{pack_id}-{family_key}",
            skill_names=family_skill_names,
            reason=reason,
        )
        for family_key, family_skill_names in _family_groups(pack_id, skill_names)
    )


def _family_groups(
    pack_id: str, skill_names: tuple[str, ...]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped = _group_by_family_depth(pack_id, skill_names, depth=1)
    stable_groups: list[tuple[str, tuple[str, ...]]] = []

    for family_key, family_skill_names in sorted(grouped.items()):
        if len(family_skill_names) <= 20:
            stable_groups.append((family_key, family_skill_names))
        else:
            stable_groups.extend(
                _deepen_family_groups(pack_id, family_skill_names, depth=2)
            )

    return tuple(stable_groups)


def _deepen_family_groups(
    pack_id: str, skill_names: tuple[str, ...], depth: int
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped = _group_by_family_depth(pack_id, skill_names, depth=depth)
    stable_groups: list[tuple[str, tuple[str, ...]]] = []

    for family_key, family_skill_names in sorted(grouped.items()):
        if len(family_skill_names) <= 20 or depth >= _max_family_depth(
            pack_id, family_skill_names
        ):
            stable_groups.append((family_key, family_skill_names))
        else:
            stable_groups.extend(
                _deepen_family_groups(pack_id, family_skill_names, depth=depth + 1)
            )

    return tuple(stable_groups)


def _group_by_family_depth(
    pack_id: str, skill_names: tuple[str, ...], depth: int
) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = defaultdict(list)

    for skill_name in skill_names:
        family_key = _family_key(pack_id, skill_name, depth)
        groups[family_key].append(skill_name)

    return {
        family_key: tuple(sorted(family_skill_names))
        for family_key, family_skill_names in groups.items()
    }


def _family_key(pack_id: str, skill_name: str, depth: int) -> str:
    tokens = _family_tokens(pack_id, skill_name)
    return "-".join(tokens[: min(depth, len(tokens))])


def _family_tokens(pack_id: str, skill_name: str) -> tuple[str, ...]:
    for prefix in _functional_prefixes(pack_id):
        if skill_name.startswith(prefix):
            skill_name = skill_name[len(prefix) :]
            break

    return tuple(token for token in skill_name.split("-") if token)


def _functional_prefixes(pack_id: str) -> tuple[str, ...]:
    if pack_id == "game-design":
        return ("game-",)
    return (f"{pack_id}-",)


def _max_family_depth(pack_id: str, skill_names: tuple[str, ...]) -> int:
    return max(len(_family_tokens(pack_id, skill_name)) for skill_name in skill_names)


def _matching_skills(
    skills: list[ScannedSkill],
    keywords: tuple[str, ...],
    *,
    exact_names: Collection[str] = (),
) -> tuple[ScannedSkill, ...]:
    matches: list[ScannedSkill] = []

    for skill in skills:
        if skill.name in exact_names:
            matches.append(skill)
            continue

        head_text = _skill_head_text(skill)
        if any(keyword in head_text for keyword in keywords):
            matches.append(skill)

    return tuple(matches)


def _skill_head_text(skill: ScannedSkill) -> str:
    return f"{skill.name}\n{skill.description}".lower()
