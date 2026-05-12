from __future__ import annotations

from pathlib import Path

import pytest

from sos.apply import _validate_archive_operations, _is_plugin_cache_path
from sos.models import OperationKind, PackManifest, SkillEntry, WriteOperation, WritePlan


def _make_plan(operations: tuple[WriteOperation, ...]) -> WritePlan:
    return WritePlan(plan_id="plan-test", host="claude", operations=operations)


def _make_manifest(active_root: Path) -> PackManifest:
    return PackManifest(
        id="demo",
        display_name="Demo",
        pointer_skill="sos-demo",
        host="claude",
        skills=(
            SkillEntry(
                name="demo-skill",
                source_path=active_root / "demo-skill",
                vault_path=active_root.parent / "vault" / "demo" / "demo-skill",
            ),
        ),
    )


def test_validate_archive_operations_accepts_well_formed_op(tmp_path):
    active_root = tmp_path / "skills"
    archive_target = active_root / ".sos-archive" / "demo" / "demo-skill"
    op = WriteOperation(
        OperationKind.MOVE_TO_ARCHIVE,
        source=active_root / "demo-skill",
        target=archive_target,
        metadata={"pack_id": "demo", "skill_name": "demo-skill", "host": "claude"},
    )
    plan = _make_plan((op,))
    result = _validate_archive_operations(plan, active_root, (_make_manifest(active_root),))
    assert result == (op,)


def test_validate_archive_operations_rejects_target_outside_archive(tmp_path):
    active_root = tmp_path / "skills"
    op = WriteOperation(
        OperationKind.MOVE_TO_ARCHIVE,
        source=active_root / "demo-skill",
        target=active_root / "elsewhere" / "demo-skill",
        metadata={"pack_id": "demo", "skill_name": "demo-skill", "host": "claude"},
    )
    plan = _make_plan((op,))
    with pytest.raises(ValueError, match="archive"):
        _validate_archive_operations(plan, active_root, (_make_manifest(active_root),))


def test_validate_archive_operations_rejects_source_outside_root(tmp_path):
    active_root = tmp_path / "skills"
    other_root = tmp_path / "other"
    op = WriteOperation(
        OperationKind.MOVE_TO_ARCHIVE,
        source=other_root / "demo-skill",
        target=active_root / ".sos-archive" / "demo" / "demo-skill",
        metadata={"pack_id": "demo", "skill_name": "demo-skill", "host": "claude"},
    )
    plan = _make_plan((op,))
    with pytest.raises(ValueError, match="archive"):
        _validate_archive_operations(plan, active_root, (_make_manifest(active_root),))


def test_plugin_cache_path_includes_claude_plugin_cache(tmp_path):
    claude_plugin_path = tmp_path / ".claude" / "plugins" / "cache" / "some-skill"
    codex_plugin_path = tmp_path / ".codex" / "plugins" / "cache" / "some-skill"
    other_path = tmp_path / ".claude" / "skills" / "some-skill"

    assert _is_plugin_cache_path(claude_plugin_path) is True
    assert _is_plugin_cache_path(codex_plugin_path) is True
    assert _is_plugin_cache_path(other_path) is False


def test_validate_archive_operations_rejects_plugin_cache_source(tmp_path):
    active_root = tmp_path / ".claude" / "plugins" / "cache"
    active_root.mkdir(parents=True)
    op = WriteOperation(
        OperationKind.MOVE_TO_ARCHIVE,
        source=active_root / "demo-skill",
        target=active_root / ".sos-archive" / "demo" / "demo-skill",
        metadata={"pack_id": "demo", "skill_name": "demo-skill", "host": "claude"},
    )
    plan = _make_plan((op,))
    manifest = PackManifest(
        id="demo",
        display_name="Demo",
        pointer_skill="sos-demo",
        host="claude",
        skills=(
            SkillEntry(
                name="demo-skill",
                source_path=active_root / "demo-skill",
                vault_path=tmp_path / "vault" / "demo" / "demo-skill",
            ),
        ),
    )
    with pytest.raises(ValueError, match="plugin cache"):
        _validate_archive_operations(plan, active_root, (manifest,))


def test_validate_archive_operations_rejects_wrong_host_metadata(tmp_path):
    active_root = tmp_path / "skills"
    archive_target = active_root / ".sos-archive" / "demo" / "demo-skill"
    op = WriteOperation(
        OperationKind.MOVE_TO_ARCHIVE,
        source=active_root / "demo-skill",
        target=archive_target,
        metadata={"pack_id": "demo", "skill_name": "demo-skill", "host": "codex"},
    )
    plan = _make_plan((op,))
    with pytest.raises(ValueError, match="host=claude"):
        _validate_archive_operations(plan, active_root, (_make_manifest(active_root),))


def test_apply_moves_source_into_sos_archive(tmp_path):
    """End-to-end: apply moves source skill folder into <root>/.sos-archive/<pack>/<name>/."""
    from sos.apply import apply_write_plan
    from sos.planner import build_pack_apply_plan
    from sos.paths import RuntimePaths
    from sos.propose import PackProposal

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    demo_dir = skill_root / "demo-skill"
    demo_dir.mkdir()
    (demo_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\nbody\n",
        encoding="utf-8",
    )
    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    proposals = (PackProposal(pack_id="demo", skill_names=("demo-skill",), reason="test"),)
    plan = build_pack_apply_plan(
        runtime_paths, skill_root, codex_config_path, proposals, host="claude"
    )

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        skill_root,
        apply=True,
        host="claude",
    )

    assert result.status == "applied"
    assert not (skill_root / "demo-skill").exists()
    archived = skill_root / ".sos-archive" / "demo" / "demo-skill"
    assert archived.is_dir()
    assert (archived / "SKILL.md").is_file()


def test_apply_rollback_moves_archive_back_on_failure(tmp_path, monkeypatch):
    """If a later phase fails after MOVE_TO_ARCHIVE, the archived folder is moved back."""
    from sos.apply import apply_write_plan
    from sos.planner import build_pack_apply_plan
    from sos.paths import RuntimePaths
    from sos.propose import PackProposal
    from sos import apply as apply_module

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    demo_dir = skill_root / "demo-skill"
    demo_dir.mkdir()
    (demo_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n",
        encoding="utf-8",
    )
    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    proposals = (PackProposal(pack_id="demo", skill_names=("demo-skill",), reason="test"),)
    plan = build_pack_apply_plan(
        runtime_paths, skill_root, codex_config_path, proposals, host="claude"
    )

    # Force failure by wrapping the executor to do its work then raise.
    original_execute = apply_module._execute_move_to_archive

    def failing_execute(operation, journal):
        original_execute(operation, journal)
        raise RuntimeError("simulated mid-apply failure")

    monkeypatch.setattr(apply_module, "_execute_move_to_archive", failing_execute)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        skill_root,
        apply=True,
        host="claude",
    )

    assert result.status == "failed"
    assert (skill_root / "demo-skill" / "SKILL.md").is_file()
    archived = skill_root / ".sos-archive" / "demo" / "demo-skill"
    assert not archived.exists()
