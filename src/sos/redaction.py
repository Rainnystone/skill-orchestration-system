from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sos.models import WritePlan
from sos.paths import RuntimePaths
from sos.planner import summarize_write_plan


def redact_local_paths(text: str, replacements: Iterable[tuple[Path, str]]) -> str:
    """Replace local path strings in *text* with opaque labels."""
    redacted = text
    path_replacements: list[tuple[str, str]] = []
    for path, replacement in replacements:
        for variant in path_variants(path):
            path_replacements.append((variant, replacement))
    for variant, replacement in sorted(
        path_replacements,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        redacted = redacted.replace(variant, replacement)
    return redacted.replace("\\", "/")


def path_variants(path: Path) -> tuple[str, ...]:
    """Return string variants of *path* (raw, expanded, resolved) for redaction matching."""
    candidates = (
        path,
        path.expanduser(),
        path.expanduser().resolve(strict=False),
    )
    variants: set[str] = set()
    for candidate in candidates:
        variants.add(str(candidate))
        variants.add(candidate.as_posix())
    return tuple(variant for variant in variants if variant)


def redacted_runtime_path(path: str | Path, runtime_paths: RuntimePaths) -> str:
    """Redact a runtime path string, replacing the runtime root with RUNTIME_ROOT."""
    return redact_local_paths(str(path), ((runtime_paths.root, "RUNTIME_ROOT"),))


def redacted_recommendation_plan_summary(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    workspace_root: str | Path,
    *,
    plan_path: str | Path | None = None,
) -> str:
    """Produce a redacted summary of a recommendation plan for user-facing output."""
    replacements: list[tuple[Path, str]] = [
        (Path(workspace_root), "WORKSPACE_ROOT"),
        (runtime_paths.root, "RUNTIME_ROOT"),
    ]
    if plan_path is not None:
        replacements.append((Path(plan_path), "WORKSPACE_PLAN"))
    return redact_local_paths(summarize_write_plan(plan), replacements)
