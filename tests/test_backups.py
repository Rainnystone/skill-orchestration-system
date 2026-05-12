from pathlib import Path

import pytest

import sos.backups as backups
from sos.backups import create_backup, list_backups, prune_backups, restore_backup
from sos.paths import RuntimePaths
from sos.toml_io import write_toml


def test_create_backup_records_config_and_vault_snapshot_with_id(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Original\n")

    record = create_backup(runtime_paths, config_path, vault_root, "before apply")

    assert record.backup_id
    assert record.metadata["backup_id"] == record.backup_id
    assert record.metadata["reason"] == "before apply"
    assert record.config_path is not None
    assert record.config_path.read_text(encoding="utf-8") == "enabled = true\n"
    assert record.metadata["config_snapshot_path"] == record.config_path.as_posix()
    assert record.vault_path is not None
    assert (record.vault_path / "SKILL.md").read_text(encoding="utf-8") == "# Original\n"
    assert record.metadata["vault_snapshot_path"] == record.vault_path.as_posix()


def test_restore_backup_restores_config_and_vault_state(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Original\n")
    record = create_backup(runtime_paths, config_path, vault_root, "before mutation")
    config_path.write_text("enabled = false\n", encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")

    restored = restore_backup(runtime_paths, record.backup_id, config_path, vault_root, apply=True)

    assert restored.backup_id == record.backup_id
    assert config_path.read_text(encoding="utf-8") == "enabled = true\n"
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Original\n"


def test_restore_backup_rolls_back_config_when_vault_restore_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Original\n")
    record = create_backup(runtime_paths, config_path, vault_root, "before mutation")
    config_path.write_text("enabled = false\n", encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")

    def fail_vault_restore(source: Path, target: Path) -> None:
        raise RuntimeError("vault restore failed")

    monkeypatch.setattr(backups, "_replace_directory_atomic", fail_vault_restore)

    with pytest.raises(RuntimeError, match="vault restore failed"):
        restore_backup(runtime_paths, record.backup_id, config_path, vault_root, apply=True)

    assert config_path.read_text(encoding="utf-8") == "enabled = false\n"


def test_restore_backup_apply_false_does_not_write(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Original\n")
    record = create_backup(runtime_paths, config_path, vault_root, "before mutation")
    config_path.write_text("enabled = false\n", encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")

    restored = restore_backup(runtime_paths, record.backup_id, config_path, vault_root, apply=False)

    assert restored.backup_id == record.backup_id
    assert config_path.read_text(encoding="utf-8") == "enabled = false\n"
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Changed\n"


def test_restore_backup_rejects_unsafe_backup_id_before_reading_outside_metadata(
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(
        tmp_path,
        "enabled = false\n",
        "# Changed\n",
    )
    runtime_paths.backups.mkdir(parents=True)
    outside_dir = runtime_paths.root / "outside"
    outside_snapshot = tmp_path / "outside-config.toml"
    outside_snapshot.write_text("enabled = true\n", encoding="utf-8")
    outside_vault_snapshot = tmp_path / "outside-vault"
    outside_vault_snapshot.mkdir()
    (outside_vault_snapshot / "SKILL.md").write_text("# Outside\n", encoding="utf-8")
    write_toml(
        outside_dir / "metadata.toml",
        {
            "backup_id": "outside",
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "outside",
            "config_snapshot_path": str(outside_snapshot),
            "vault_snapshot_path": str(outside_vault_snapshot),
        },
    )

    with pytest.raises(ValueError, match="backup_id"):
        restore_backup(runtime_paths, "../outside", config_path, vault_root, apply=True)

    assert config_path.read_text(encoding="utf-8") == "enabled = false\n"
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Changed\n"


def test_list_backups_returns_newest_first(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Original\n")

    first = create_backup(runtime_paths, config_path, vault_root, "first")
    second = create_backup(runtime_paths, config_path, vault_root, "second")

    assert first.backup_id != second.backup_id
    assert [record.backup_id for record in list_backups(runtime_paths)] == [
        second.backup_id,
        first.backup_id,
    ]


def test_prune_backups_keeps_newest_20(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    backup_ids = tuple(f"backup-20260424T1200{index:02d}000000Z" for index in range(22))
    for index, backup_id in enumerate(backup_ids):
        backup_dir = runtime_paths.backups / backup_id
        write_toml(
            backup_dir / "metadata.toml",
            {
                "backup_id": backup_id,
                "created_at": f"2026-04-24T12:00:{index:02d}+00:00",
                "reason": "seeded",
            },
        )

    remaining = prune_backups(runtime_paths, keep=20, apply=True)

    assert [record.backup_id for record in remaining] == list(reversed(backup_ids[2:]))
    assert sorted(path.name for path in runtime_paths.backups.iterdir()) == sorted(backup_ids[2:])


def test_prune_backups_rejects_metadata_id_that_does_not_match_directory(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    backup_dir = runtime_paths.backups / "backup-safe"
    outside_dir = runtime_paths.root / "outside"
    outside_file = outside_dir / "keep.txt"
    outside_file.parent.mkdir(parents=True)
    outside_file.write_text("do not delete\n", encoding="utf-8")
    write_toml(
        backup_dir / "metadata.toml",
        {
            "backup_id": "../outside",
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "seeded",
        },
    )

    with pytest.raises(ValueError):
        prune_backups(runtime_paths, keep=0, apply=True)

    assert outside_file.read_text(encoding="utf-8") == "do not delete\n"


def test_prune_backups_apply_false_does_not_delete(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    backup_ids = tuple(f"backup-20260424T1200{index:02d}000000Z" for index in range(3))
    for index, backup_id in enumerate(backup_ids):
        write_toml(
            runtime_paths.backups / backup_id / "metadata.toml",
            {
                "backup_id": backup_id,
                "created_at": f"2026-04-24T12:00:{index:02d}+00:00",
                "reason": "seeded",
            },
        )

    remaining = prune_backups(runtime_paths, keep=1, apply=False)

    assert [record.backup_id for record in remaining] == [backup_ids[-1]]
    assert sorted(path.name for path in runtime_paths.backups.iterdir()) == sorted(backup_ids)


def test_backup_metadata_paths_are_posix_on_all_platforms(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Test\n")

    record = create_backup(runtime_paths, config_path, vault_root, "posix test")

    if record.config_path is not None:
        assert "\\" not in str(record.metadata["config_snapshot_path"])
    if record.vault_path is not None:
        assert "\\" not in str(record.metadata["vault_snapshot_path"])


def test_backup_with_posix_metadata_round_trips_through_restore(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    config_path, vault_root = _write_config_and_vault(tmp_path, "enabled = true\n", "# Original\n")
    create_backup(runtime_paths, config_path, vault_root, "before mutation")
    config_path.write_text("enabled = false\n", encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")

    records = list_backups(runtime_paths)
    assert len(records) == 1

    restored = restore_backup(
        runtime_paths, records[0].backup_id, config_path, vault_root, apply=True
    )
    assert config_path.read_text(encoding="utf-8") == "enabled = true\n"
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Original\n"


def _write_config_and_vault(
    tmp_path: Path,
    config_text: str,
    skill_text: str,
) -> tuple[Path, Path]:
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_text, encoding="utf-8")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "SKILL.md").write_text(skill_text, encoding="utf-8")
    return config_path, vault_root


def test_validate_backup_id_component_rejects_backslash():
    from sos.backups import _validate_backup_id_component
    with pytest.raises(ValueError, match="unsafe"):
        _validate_backup_id_component("..\\outside")


def test_restore_claude_pack_moves_archive_back(tmp_path):
    """End-to-end: apply Claude plan, then restore moves archive contents back to source."""
    from sos.apply import apply_write_plan
    from sos.planner import build_pack_apply_plan
    from sos.paths import RuntimePaths
    from sos.propose import PackProposal
    from sos.backups import restore_backup
    from sos.toml_io import read_toml, write_toml

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo-skill").mkdir()
    (skill_root / "demo-skill" / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    proposals = (PackProposal(pack_id="demo", skill_names=("demo-skill",), reason="test"),)
    plan = build_pack_apply_plan(
        runtime_paths, skill_root, codex_config_path, proposals, host="claude"
    )
    apply_result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        skill_root,
        apply=True,
        host="claude",
    )
    assert apply_result.status == "applied"
    assert not (skill_root / "demo-skill" / "SKILL.md").is_file()

    # Annotate metadata as the CLI would.
    backup_dir = runtime_paths.backups / apply_result.backup_id
    metadata_path = backup_dir / "metadata.toml"
    metadata = read_toml(metadata_path)
    write_toml(metadata_path, {
        **metadata,
        "vault_root": str(runtime_paths.vault),
        "active_skill_root": str(skill_root),
        "host": "claude",
    })

    restore_backup(
        runtime_paths,
        apply_result.backup_id,
        codex_config_path,
        runtime_paths.vault,
        apply=True,
    )
    assert (skill_root / "demo-skill" / "SKILL.md").is_file()
    archived = skill_root / ".sos-archive" / "demo" / "demo-skill"
    assert not archived.exists()


def test_restore_refuses_when_archive_missing(tmp_path):
    """Restore should error if the .sos-archive entry is gone (user manually deleted it)."""
    import shutil
    import pytest
    from sos.apply import apply_write_plan
    from sos.planner import build_pack_apply_plan
    from sos.paths import RuntimePaths
    from sos.propose import PackProposal
    from sos.backups import restore_backup
    from sos.toml_io import read_toml, write_toml

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo-skill").mkdir()
    (skill_root / "demo-skill" / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    proposals = (PackProposal(pack_id="demo", skill_names=("demo-skill",), reason="test"),)
    plan = build_pack_apply_plan(
        runtime_paths, skill_root, codex_config_path, proposals, host="claude"
    )
    apply_result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        skill_root,
        apply=True,
        host="claude",
    )

    metadata_path = runtime_paths.backups / apply_result.backup_id / "metadata.toml"
    metadata = read_toml(metadata_path)
    write_toml(metadata_path, {
        **metadata,
        "vault_root": str(runtime_paths.vault),
        "active_skill_root": str(skill_root),
        "host": "claude",
    })

    # Manually nuke the archive
    shutil.rmtree(skill_root / ".sos-archive")

    with pytest.raises(ValueError, match="archive"):
        restore_backup(
            runtime_paths,
            apply_result.backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )
