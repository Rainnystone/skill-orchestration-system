from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sos.models import PackManifest
from sos.pack_inspect import list_pack_manifests
from sos.paths import RuntimePaths
from sos.recommendation_store import (
    SelectionEvent,
    learned_reference_path,
    load_selection_events,
    workspace_id_for_path,
)
from sos.workspace_scan import WorkspaceSignal, scan_workspace


_KIND_KEYWORDS = {
    "docs": ("doc", "docs", "document", "documents", "pdf", "markdown", "readme", "text"),
    "browser": ("browser", "web", "page", "pages", "site", "sites"),
    "python": ("python", "py", "pytest"),
    "data": ("data", "csv", "json", "sql", "xlsx", "tsv", "table"),
    "design": ("design", "image", "images", "figma", "fig", "sketch", "asset"),
}


@dataclass(frozen=True)
class RecommendationContext:
    runtime_paths: RuntimePaths
    workspace_root: Path
    workspace_signal: WorkspaceSignal
    intent: str
    pack_manifests: tuple[PackManifest, ...]
    learned_reference: str
    selection_events: tuple[SelectionEvent, ...]


@dataclass(frozen=True)
class Recommendation:
    pack_id: str
    display_name: str
    reason: str
    skill_names: tuple[str, ...]
    score: int


def build_recommendation_context(
    runtime_paths: RuntimePaths,
    workspace_root: str | Path,
    intent: str = "",
) -> RecommendationContext:
    learned_path = learned_reference_path(runtime_paths)
    return RecommendationContext(
        runtime_paths=runtime_paths,
        workspace_root=Path(workspace_root).expanduser(),
        workspace_signal=scan_workspace(workspace_root),
        intent=intent,
        pack_manifests=list_pack_manifests(runtime_paths),
        learned_reference=learned_path.read_text(encoding="utf-8") if learned_path.is_file() else "",
        selection_events=load_selection_events(runtime_paths),
    )


def recommend_packs(
    context: RecommendationContext,
    limit: int = 3,
) -> tuple[Recommendation, ...]:
    if limit <= 0:
        return ()

    local_selection_counts = _accepted_local_selection_counts(
        context.selection_events,
        context.workspace_root,
    )
    recommendations = [
        _score_manifest(
            manifest,
            context.workspace_signal,
            context.intent,
            context.learned_reference,
            local_selection_counts,
        )
        for manifest in context.pack_manifests
    ]
    ranked = sorted(recommendations, key=lambda item: (-item.score, item.pack_id))
    return tuple(ranked[:limit])


def _score_manifest(
    manifest: PackManifest,
    workspace_signal: WorkspaceSignal,
    intent: str,
    learned_reference: str,
    local_selection_counts: Counter[str],
) -> Recommendation:
    score = 0
    reasons: list[str] = []
    search_blob = _manifest_search_blob(manifest)

    workspace_score = _workspace_score(workspace_signal, search_blob)
    if workspace_score:
        score += workspace_score
        reasons.append("workspace signals")

    intent_score = _text_match_score(intent, search_blob, weight=4)
    if intent_score:
        score += intent_score
        reasons.append("intent match")

    learned_score = _learned_reference_score(learned_reference, manifest)
    if learned_score:
        score += learned_score
        reasons.append("learned reference")

    accepted_count = local_selection_counts.get(manifest.id, 0)
    if accepted_count:
        score += accepted_count * 3
        reasons.append("accepted local selections")

    if not reasons:
        reasons.append("manifest metadata")

    return Recommendation(
        pack_id=manifest.id,
        display_name=manifest.display_name,
        reason="; ".join(reasons),
        skill_names=tuple(skill.name for skill in manifest.skills),
        score=score,
    )


def _workspace_score(workspace_signal: WorkspaceSignal, search_blob: str) -> int:
    score = 0
    search_tokens = frozenset(_tokens(search_blob))
    for kind in workspace_signal.kinds:
        if kind == "mixed":
            continue
        keywords = _KIND_KEYWORDS.get(kind, ())
        if any(_keyword_matches(search_blob, search_tokens, keyword) for keyword in keywords):
            score += 6
    if "readme" in workspace_signal.markers and "readme" in search_blob:
        score += 1
    if "docs_dir" in workspace_signal.markers and "docs" in search_blob:
        score += 1
    return score


def _text_match_score(text: str, search_blob: str, weight: int) -> int:
    tokens = _tokens(text)
    if not tokens:
        return 0
    return sum(weight for token in tokens if token in search_blob)


def _learned_reference_score(
    learned_reference: str,
    manifest: PackManifest,
) -> int:
    if not learned_reference:
        return 0
    preferred_targets = _preferred_targets(learned_reference)
    score = 0
    if manifest.id.lower() in preferred_targets:
        score += 5
    for alias in manifest.aliases:
        if alias.lower() in preferred_targets:
            score += 1
    return score


def _accepted_local_selection_counts(
    events: Iterable[SelectionEvent],
    workspace_root: Path,
) -> Counter[str]:
    workspace_id = workspace_id_for_path(workspace_root)
    counts: Counter[str] = Counter()
    for event in events:
        if event.workspace_id != workspace_id:
            continue
        if event.selection_source != "user_accepted" or event.outcome != "activated":
            continue
        for pack_id in event.selected_pack_ids:
            counts[pack_id] += 1
    return counts


def _manifest_search_blob(manifest: PackManifest) -> str:
    parts = [
        manifest.id,
        manifest.display_name,
        manifest.description,
        *manifest.aliases,
    ]
    for skill in manifest.skills:
        parts.extend((skill.name, skill.description))
    return " ".join(part.lower() for part in parts if part)


def _keyword_matches(search_blob: str, search_tokens: frozenset[str], keyword: str) -> bool:
    if " " in keyword:
        return keyword in search_blob
    return keyword in search_tokens


def _preferred_targets(learned_reference: str) -> frozenset[str]:
    targets: set[str] = set()
    prefix = "prefer recommending:"
    for line in learned_reference.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith(prefix):
            continue
        values = stripped[len(prefix) :].split(",")
        for value in values:
            cleaned = value.strip().lower()
            if cleaned:
                targets.add(cleaned)
    return frozenset(targets)


def _tokens(text: str) -> tuple[str, ...]:
    cleaned = text.lower()
    for character in ",.;:/\\-_()[]{}":
        cleaned = cleaned.replace(character, " ")
    return tuple(token for token in cleaned.split() if token)
