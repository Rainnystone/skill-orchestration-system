from __future__ import annotations

from pathlib import Path

from sos.models import (
    OperationKind,
    PackManifest,
    SkillEntry,
    WriteOperation,
    WritePlan,
)


def test_operation_kind_includes_move_and_restore_from_archive():
    assert OperationKind.MOVE_TO_ARCHIVE.value == "move_to_archive"
    assert OperationKind.RESTORE_FROM_ARCHIVE.value == "restore_from_archive"


def test_write_plan_defaults_to_codex_host():
    plan = WritePlan(plan_id="plan-test")
    assert plan.host == "codex"


def test_write_plan_accepts_claude_host():
    plan = WritePlan(plan_id="plan-test", host="claude")
    assert plan.host == "claude"


def test_pack_manifest_defaults_to_codex_host():
    manifest = PackManifest(id="x", display_name="X", pointer_skill="sos-x")
    assert manifest.host == "codex"


def test_skill_entry_archived_source_path_defaults_none():
    entry = SkillEntry(
        name="x",
        source_path=Path("/tmp/x"),
        vault_path=Path("/tmp/vault/x"),
    )
    assert entry.archived_source_path is None


def test_skill_entry_accepts_archived_source_path():
    entry = SkillEntry(
        name="x",
        source_path=Path("/tmp/x"),
        vault_path=Path("/tmp/vault/x"),
        archived_source_path=Path("/tmp/.sos-archive/pack/x"),
    )
    assert entry.archived_source_path == Path("/tmp/.sos-archive/pack/x")
