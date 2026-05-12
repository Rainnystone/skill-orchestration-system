from pathlib import Path

import sos.recommendation_store as recommendation_store
from sos.manifest import save_registry
from sos.models import PackManifest, Registry, SkillEntry
from sos.paths import RuntimePaths
from sos.recommendation_engine import build_recommendation_context, recommend_packs


def test_docs_workspace_ranks_docs_pack_first(tmp_path: Path) -> None:
    runtime_paths = _write_registry(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Project\n", encoding="utf-8")
    (workspace / "reference.pdf").write_bytes(b"%PDF")

    context = build_recommendation_context(runtime_paths, workspace)
    recommendations = recommend_packs(context)

    assert len(recommendations) <= 3
    assert recommendations[0].pack_id == "docs"
    assert recommendations[0].skill_names == ("documents", "pdf")
    assert "workspace signals" in recommendations[0].reason


def test_browser_intent_ranks_browser_first_for_sparse_workspace(tmp_path: Path) -> None:
    runtime_paths = _write_registry(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    context = build_recommendation_context(
        runtime_paths,
        workspace,
        intent="open browser and inspect a page",
    )
    recommendations = recommend_packs(context)

    assert recommendations[0].pack_id == "browser"


def test_recent_accepted_local_events_add_browser_soft_hint(tmp_path: Path) -> None:
    runtime_paths = _write_registry(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workspace_id = recommendation_store.workspace_id_for_path(workspace)

    for index in range(3):
        recommendation_store.append_selection_event(
            runtime_paths,
            recommendation_store.SelectionEvent(
                schema_version=1,
                created_at=f"2026-05-12T10:00:0{index}+00:00",
                workspace_id=workspace_id,
                scenario_label="browser help",
                scenario_tags=("browser",),
                selected_pack_ids=("browser",),
                selected_skill_names=("open-browser",),
                manifest_fingerprint="sha256:test",
                selection_source="user_accepted",
                outcome="activated",
            ),
        )

    context = build_recommendation_context(runtime_paths, workspace)
    recommendations = recommend_packs(context)

    browser = next(item for item in recommendations if item.pack_id == "browser")
    assert "accepted local selections" in browser.reason


def test_build_context_does_not_create_learned_reference_when_missing(tmp_path: Path) -> None:
    runtime_paths = _write_registry(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    context = build_recommendation_context(runtime_paths, workspace)

    assert context.learned_reference == ""
    assert not recommendation_store.learned_reference_path(runtime_paths).exists()


def _write_registry(tmp_path: Path) -> RuntimePaths:
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    registry_path = runtime_paths.state / "registry.toml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    save_registry(
        registry_path,
        Registry(
            packs=(
                PackManifest(
                    id="docs",
                    display_name="Documents",
                    pointer_skill="sos-docs",
                    aliases=("documents", "pdf"),
                    description="Work with documents, PDF files, and written references.",
                    skills=(
                        SkillEntry(
                            name="documents",
                            description="Create and edit docx documents.",
                            source_path=Path("skills/documents/SKILL.md"),
                            vault_path=Path("vault/documents/SKILL.md"),
                        ),
                        SkillEntry(
                            name="pdf",
                            description="Review and generate PDF files.",
                            source_path=Path("skills/pdf/SKILL.md"),
                            vault_path=Path("vault/pdf/SKILL.md"),
                        ),
                    ),
                ),
                PackManifest(
                    id="browser",
                    display_name="Browser",
                    pointer_skill="sos-browser",
                    aliases=("web", "browse"),
                    description="Open pages, inspect web apps, and test browser flows.",
                    skills=(
                        SkillEntry(
                            name="open-browser",
                            description="Navigate and inspect browser pages.",
                            source_path=Path("skills/browser/SKILL.md"),
                            vault_path=Path("vault/browser/SKILL.md"),
                        ),
                    ),
                ),
            ),
        ),
    )
    return runtime_paths
