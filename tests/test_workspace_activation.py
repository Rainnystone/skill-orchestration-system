from __future__ import annotations

import re
from pathlib import Path

import pytest

from sos.backups import list_backups, restore_backup
from sos.manifest import save_pack_manifest, save_registry
from sos.models import (
    OperationKind,
    PackManifest,
    Registry,
    SkillEntry,
    WriteOperation,
    WritePlan,
)
from sos.paths import RuntimePaths
from sos.planner import load_write_plan, serialize_write_plan
from sos.recommendation_store import (
    ASAHINA_EMPTY_REFERENCE,
    learned_reference_path,
)
from sos.workspace_activation import (
    apply_workspace_activation_plan,
    build_workspace_activation_plan,
)


def _runtime_paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths.from_root(tmp_path / ".sos")


def _workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


def _write_source_skill(root: Path, name: str) -> Path:
    skill_root = root / name
    skill_root.mkdir(parents=True, exist_ok=True)
    (skill_root / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} source skill.\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill_root


def _setup_runtime_docs_pack(tmp_path: Path) -> tuple[RuntimePaths, PackManifest]:
    runtime_paths = _runtime_paths(tmp_path)
    source_root = tmp_path / "source-skills"
    source_skill = _write_source_skill(source_root, "documents")
    manifest = PackManifest(
        id="docs",
        display_name="Docs",
        pointer_skill="sos-docs",
        aliases=("docs",),
        description="Use this for documentation skills managed by SOS.",
        vault_root=runtime_paths.vault / "docs",
        skills=(
            SkillEntry(
                name="documents",
                source_path=source_skill,
                vault_path=runtime_paths.vault / "docs" / "documents",
                description="documents source skill.",
            ),
        ),
    )
    save_pack_manifest(runtime_paths.packs / "docs.toml", manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(
            packs=(manifest,),
            active_pointers=("sos-docs",),
            aliases={"docs": "docs"},
        ),
    )
    return runtime_paths, manifest


def _retarget_workspace_plan(plan: WritePlan, workspace_skill_root: Path) -> WritePlan:
    operations: list[WriteOperation] = []
    for operation in plan.operations:
        if operation.kind in {
            OperationKind.WRITE_WORKSPACE_SKILL,
            OperationKind.WRITE_POINTER,
        }:
            skill_name = operation.target.parent.name
            metadata = dict(operation.metadata)
            metadata["workspace_skill_root"] = str(workspace_skill_root)
            operations.append(
                WriteOperation(
                    operation.kind,
                    source=operation.source,
                    target=workspace_skill_root / skill_name / "SKILL.md",
                    metadata=metadata,
                )
            )
        else:
            operations.append(operation)
    return WritePlan(
        plan_id=plan.plan_id,
        pack_ids=plan.pack_ids,
        operations=tuple(operations),
        requires_apply=plan.requires_apply,
        delete_source_requested=plan.delete_source_requested,
        second_confirmation=plan.second_confirmation,
        host=plan.host,
    )


def test_workspace_activation_dry_run_does_not_create_workspace_or_recommendation_dirs(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)

    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))
    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=False,
    )

    assert plan.requires_apply is True
    assert plan.pack_ids == ("docs",)
    assert result.status == "planned"
    assert not (workspace_root / ".agents").exists()
    assert not runtime_paths.state.joinpath("recommendations").exists()


def test_workspace_activation_apply_writes_workspace_skills_pointer_and_stub(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)

    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))
    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=True,
    )

    workspace_skill_root = workspace_root / ".agents" / "skills"
    assert result.status == "applied"
    assert (workspace_skill_root / "sos-nagato" / "SKILL.md").exists()
    assert (workspace_skill_root / "sos-asahina" / "SKILL.md").exists()
    assert (workspace_skill_root / "sos-docs" / "SKILL.md").exists()
    assert learned_reference_path(runtime_paths).read_text(encoding="utf-8") == (
        ASAHINA_EMPTY_REFERENCE
    )


def test_workspace_activation_apply_creates_restorable_backup_for_existing_targets(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    workspace_skill_root = workspace_root / ".agents" / "skills"
    existing_nagato = workspace_skill_root / "sos-nagato" / "SKILL.md"
    existing_nagato.parent.mkdir(parents=True, exist_ok=True)
    existing_nagato.write_text("ORIGINAL NAGATO\n", encoding="utf-8")
    learned_path = learned_reference_path(runtime_paths)
    learned_path.parent.mkdir(parents=True, exist_ok=True)
    learned_path.write_text("ORIGINAL LEARNED\n", encoding="utf-8")
    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))

    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=True,
    )
    backups = list_backups(runtime_paths)

    assert result.status == "applied"
    assert len(backups) == 1
    assert backups[0].metadata["scope"] == "workspace_activation"
    assert existing_nagato.read_text(encoding="utf-8") != "ORIGINAL NAGATO\n"
    assert learned_path.read_text(encoding="utf-8") == "ORIGINAL LEARNED\n"

    restore_backup(
        runtime_paths,
        backups[0].backup_id,
        codex_config_path=None,
        vault_root=None,
        apply=True,
    )

    assert existing_nagato.read_text(encoding="utf-8") == "ORIGINAL NAGATO\n"
    assert learned_path.read_text(encoding="utf-8") == "ORIGINAL LEARNED\n"


def test_workspace_activation_expands_home_relative_workspace_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    plan = build_workspace_activation_plan(runtime_paths, "~/project", ("docs",))

    targets = tuple(operation.target for operation in plan.operations if operation.target)
    assert targets
    for target in targets:
        if target.name == "SKILL.md":
            assert home / "project" / ".agents" / "skills" in target.parents


def test_recommend_workspace_activation_redacts_absolute_paths_in_workspace_skills(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)

    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))
    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=True,
    )

    workspace_skill_root = workspace_root / ".agents" / "skills"
    nagato_text = (workspace_skill_root / "sos-nagato" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    asahina_text = (workspace_skill_root / "sos-asahina" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    docs_text = (workspace_skill_root / "sos-docs" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert result.status == "applied"
    for rendered in (nagato_text, asahina_text, docs_text):
        assert str(workspace_root) not in rendered
        assert str(runtime_paths.root) not in rendered
        assert str(tmp_path) not in rendered
        assert re.search(r"[A-Z]:\\\\", rendered) is None
    assert "WORKSPACE_ROOT" in nagato_text
    assert "RUNTIME_ROOT/state/recommendations/asahina-reference.md" in nagato_text
    assert "sos recommend context" in nagato_text
    assert "sos recommend learn" in asahina_text
    assert "confirm it with the user" in asahina_text
    assert "sos pack activate docs --runtime-root RUNTIME_ROOT --sync=clean-auto" in docs_text


def test_workspace_activation_rejects_unknown_pack_id(tmp_path: Path):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)

    with pytest.raises(ValueError, match="unknown pack"):
        build_workspace_activation_plan(
            runtime_paths,
            _workspace_root(tmp_path),
            ("unknown",),
        )


def test_workspace_activation_apply_rolls_back_on_asahina_render_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    workspace_skill_root = workspace_root / ".agents" / "skills"
    preexisting_nagato = workspace_skill_root / "sos-nagato" / "SKILL.md"
    preexisting_nagato.parent.mkdir(parents=True, exist_ok=True)
    preexisting_nagato.write_text("PREEXISTING NAGATO\n", encoding="utf-8")
    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))

    def fail_asahina(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("sos.workspace_activation.render_asahina_skill", fail_asahina)

    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=True,
    )

    assert result.status == "failed"
    assert result.message == "boom"
    assert preexisting_nagato.read_text(encoding="utf-8") == "PREEXISTING NAGATO\n"
    assert not (workspace_skill_root / "sos-docs").exists()


def test_workspace_activation_apply_removes_agents_skeleton_on_asahina_render_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))

    def fail_asahina(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("sos.workspace_activation.render_asahina_skill", fail_asahina)

    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=True,
    )

    assert result.status == "failed"
    assert result.message == "boom"
    assert not (workspace_root / ".agents").exists()
    assert not (workspace_root / ".agents" / "skills").exists()


def test_workspace_activation_preserves_existing_learned_reference_content(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    learned_path = learned_reference_path(runtime_paths)
    learned_path.parent.mkdir(parents=True, exist_ok=True)
    learned_path.write_text("# Existing\n", encoding="utf-8")
    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))

    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        apply=True,
    )

    assert result.status == "applied"
    assert learned_path.read_text(encoding="utf-8") == "# Existing\n"


def test_workspace_activation_rejects_tampered_workspace_root(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    workspace_root.mkdir()
    tampered_workspace_root = tmp_path / "other-workspace"
    tampered_workspace_root.mkdir()
    tampered_skill_root = tampered_workspace_root / ".agents" / "skills"
    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))
    tampered_plan = _retarget_workspace_plan(plan, tampered_skill_root)

    with pytest.raises(
        ValueError,
        match="workspace activation plan workspace root does not match",
    ):
        apply_workspace_activation_plan(
            tampered_plan,
            runtime_paths,
            workspace_root=workspace_root,
            apply=True,
        )

    assert not (tampered_workspace_root / ".agents").exists()


def test_workspace_activation_plan_round_trips_with_new_operation_kinds(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan_path = tmp_path / "workspace-activation-plan.toml"

    plan = build_workspace_activation_plan(runtime_paths, workspace_root, ("docs",))
    serialize_write_plan(plan, plan_path)
    loaded = load_write_plan(plan_path)

    assert loaded.plan_id == plan.plan_id
    assert loaded.pack_ids == ("docs",)
    assert loaded.requires_apply is True
    assert tuple(operation.kind for operation in loaded.operations) == (
        OperationKind.WRITE_WORKSPACE_SKILL,
        OperationKind.WRITE_POINTER,
        OperationKind.WRITE_WORKSPACE_SKILL,
        OperationKind.WRITE_LEARNED_REFERENCE_STUB,
    )


def test_workspace_activation_claude_plan_targets_claude_skill_root_and_round_trips(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan_path = tmp_path / "claude-workspace-plan.toml"

    plan = build_workspace_activation_plan(
        runtime_paths,
        workspace_root,
        ("docs",),
        host="claude",
    )
    serialize_write_plan(plan, plan_path)
    loaded = load_write_plan(plan_path)

    assert plan.host == "claude"
    assert loaded.host == "claude"
    skill_targets = tuple(
        operation.target
        for operation in loaded.operations
        if operation.target is not None and operation.target.name == "SKILL.md"
    )
    assert skill_targets
    for target in skill_targets:
        if target.parent.name.startswith("sos-"):
            assert workspace_root / ".claude" / "skills" in target.parents
            assert workspace_root / ".agents" / "skills" not in target.parents


def test_workspace_activation_claude_apply_writes_claude_project_skills_only(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan = build_workspace_activation_plan(
        runtime_paths,
        workspace_root,
        ("docs",),
        host="claude",
    )

    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        host="claude",
        apply=True,
    )

    claude_skill_root = workspace_root / ".claude" / "skills"
    assert result.status == "applied"
    assert (claude_skill_root / "sos-nagato" / "SKILL.md").is_file()
    assert (claude_skill_root / "sos-asahina" / "SKILL.md").is_file()
    assert (claude_skill_root / "sos-docs" / "SKILL.md").is_file()
    assert not (workspace_root / ".agents").exists()


def test_workspace_activation_apply_rejects_plan_host_mismatch_before_writing(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan = build_workspace_activation_plan(
        runtime_paths,
        workspace_root,
        ("docs",),
        host="claude",
    )

    with pytest.raises(ValueError, match="plan host"):
        apply_workspace_activation_plan(
            plan,
            runtime_paths,
            workspace_root=workspace_root,
            host="codex",
            apply=True,
        )

    assert not (workspace_root / ".claude").exists()
    assert not (workspace_root / ".agents").exists()


def test_workspace_activation_apply_rejects_codex_plan_with_explicit_claude_host_before_writing(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan = build_workspace_activation_plan(
        runtime_paths,
        workspace_root,
        ("docs",),
        host="codex",
    )

    with pytest.raises(ValueError, match="plan host"):
        apply_workspace_activation_plan(
            plan,
            runtime_paths,
            workspace_root=workspace_root,
            host="claude",
            apply=True,
        )

    assert not (workspace_root / ".agents" / "skills" / "sos-nagato").exists()
    assert not (workspace_root / ".claude" / "skills" / "sos-nagato").exists()


def test_workspace_activation_rejects_claude_plan_retargeted_to_agents_root(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    plan = build_workspace_activation_plan(
        runtime_paths,
        workspace_root,
        ("docs",),
        host="claude",
    )
    tampered_plan = _retarget_workspace_plan(
        plan,
        workspace_root / ".agents" / "skills",
    )

    with pytest.raises(ValueError, match="workspace activation plan must target workspace .claude skills root"):
        apply_workspace_activation_plan(
            tampered_plan,
            runtime_paths,
            workspace_root=workspace_root,
            host="claude",
            apply=True,
        )

    assert not (workspace_root / ".agents").exists()


def test_workspace_activation_claude_apply_creates_restorable_backup_for_existing_targets(
    tmp_path: Path,
):
    runtime_paths, _ = _setup_runtime_docs_pack(tmp_path)
    workspace_root = _workspace_root(tmp_path)
    claude_skill_root = workspace_root / ".claude" / "skills"
    existing_nagato = claude_skill_root / "sos-nagato" / "SKILL.md"
    existing_nagato.parent.mkdir(parents=True, exist_ok=True)
    existing_nagato.write_text("ORIGINAL CLAUDE NAGATO\n", encoding="utf-8")
    learned_path = learned_reference_path(runtime_paths)
    learned_path.parent.mkdir(parents=True, exist_ok=True)
    learned_path.write_text("ORIGINAL LEARNED\n", encoding="utf-8")
    plan = build_workspace_activation_plan(
        runtime_paths,
        workspace_root,
        ("docs",),
        host="claude",
    )

    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=workspace_root,
        host="claude",
        apply=True,
    )
    backups = list_backups(runtime_paths)

    assert result.status == "applied"
    assert len(backups) == 1
    assert backups[0].metadata["scope"] == "workspace_activation"
    assert backups[0].metadata["host"] == "claude"
    assert backups[0].metadata["workspace_skill_root"] == str(claude_skill_root)
    assert existing_nagato.read_text(encoding="utf-8") != "ORIGINAL CLAUDE NAGATO\n"

    restore_backup(
        runtime_paths,
        backups[0].backup_id,
        codex_config_path=None,
        vault_root=None,
        apply=True,
    )

    assert existing_nagato.read_text(encoding="utf-8") == "ORIGINAL CLAUDE NAGATO\n"
    assert learned_path.read_text(encoding="utf-8") == "ORIGINAL LEARNED\n"
