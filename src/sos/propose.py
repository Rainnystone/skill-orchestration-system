from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
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
        ("obsidian", "canvas", "json canvas", "json-canvas", "obsidian canvas"),
        "Shared source/tool family signal: Obsidian or Canvas in skill name or description.",
    ),
    (
        "game-design",
        ("browser game", "game design", "game studio", "gameplay", "phaser", "three.js", "threejs", "webgl", "sprite"),
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
        (
            "deployment",
            "deploy",
            "hosting",
            "render.com",
            "render deployment",
            "render hosting",
            "vercel",
            "docker",
            "publish",
        ),
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
        matches = _matching_skills(
            remaining,
            pack_id,
            keywords,
            exact_names=exact_names,
        )
        if matches:
            proposals.extend(
                _proposals(pack_id, tuple(skill.name for skill in matches), reason)
            )
            matched_names = {skill.name for skill in matches}
            remaining = [skill for skill in remaining if skill.name not in matched_names]

    functional_matches = _functional_group_matches(remaining)
    for pack_id, _, reason in FUNCTIONAL_GROUPS:
        matches = functional_matches[pack_id]
        if matches:
            proposals.extend(
                _proposals(pack_id, tuple(skill.name for skill in matches), reason)
            )

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
    pack_id: str,
    keywords: tuple[str, ...],
    *,
    exact_names: Collection[str] = (),
) -> tuple[ScannedSkill, ...]:
    matches: list[ScannedSkill] = []

    for skill in skills:
        if skill.name in exact_names:
            matches.append(skill)
            continue

        if pack_id == "game-design" and skill.name.startswith("game-"):
            matches.append(skill)
            continue

        head_text = _skill_head_text(skill)
        normalized_head_text = _normalized_text(head_text)
        if any(
            _matches_keyword(pack_id, keyword, normalized_head_text)
            for keyword in keywords
        ):
            matches.append(skill)

    return tuple(matches)


def _functional_group_matches(
    skills: list[ScannedSkill],
) -> dict[str, tuple[ScannedSkill, ...]]:
    grouped: dict[str, list[ScannedSkill]] = {
        pack_id: [] for pack_id, _, _ in FUNCTIONAL_GROUPS
    }

    for skill in skills:
        matched_groups = _matching_functional_groups(skill)
        if len(matched_groups) == 1:
            grouped[matched_groups[0][0]].append(skill)

    return {
        pack_id: tuple(grouped[pack_id])
        for pack_id, _, _ in FUNCTIONAL_GROUPS
    }


def _matching_functional_groups(
    skill: ScannedSkill,
) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    head_text = _skill_head_text(skill)
    normalized_head_text = _normalized_text(head_text)
    matches: list[tuple[str, tuple[str, ...], str]] = []

    for pack_id, keywords, reason in FUNCTIONAL_GROUPS:
        if any(
            _matches_keyword(pack_id, keyword, normalized_head_text)
            for keyword in keywords
        ):
            matches.append((pack_id, keywords, reason))

    return tuple(matches)


def _skill_head_text(skill: ScannedSkill) -> str:
    return f"{skill.name}\n{skill.description}".lower()


def _normalized_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _matches_keyword(
    pack_id: str,
    keyword: str,
    normalized_head_text: str,
) -> bool:
    if pack_id == "obsidian" and keyword == "canvas":
        return _matches_canvas_signal(normalized_head_text)

    return _contains_term(normalized_head_text, keyword)


def _contains_term(normalized_head_text: str, keyword: str) -> bool:
    normalized_keyword = _normalized_text(keyword)
    if not normalized_keyword:
        return False

    pattern = rf"\b{re.escape(normalized_keyword)}\b"
    return re.search(pattern, normalized_head_text) is not None


def _matches_canvas_signal(normalized_head_text: str) -> bool:
    if _contains_term(normalized_head_text, "json canvas"):
        return True
    if _contains_term(normalized_head_text, "obsidian canvas"):
        return True

    if not _contains_term(normalized_head_text, "canvas"):
        return False

    if _contains_term(normalized_head_text, "html canvas"):
        return False

    support_terms = ("obsidian", "vault", "json", "workflow", "workflows")
    return any(_contains_term(normalized_head_text, term) for term in support_terms)
