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


def test_restore_claude_rejects_target_collisions_before_moving(tmp_path: Path):
    runtime_paths, skill_root, codex_config_path, backup_id, metadata = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )
    archive_one = skill_root / ".sos-archive" / "demo" / "demo-skill"
    metadata["archive_restore_entries"] = [
        {
            "pack_id": "demo",
            "skill_name": "demo-skill",
            "archive_path": archive_one.as_posix(),
            "source_path": (skill_root / "demo-skill").as_posix(),
        },
        {
            "pack_id": "demo",
            "skill_name": "demo-skill",
            "archive_path": archive_one.as_posix(),
            "source_path": (skill_root / "demo-skill").as_posix(),
        },
    ]
    write_toml(runtime_paths.backups / backup_id / "metadata.toml", metadata)

    with pytest.raises(ValueError, match="archive restore target collision"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )

    assert archive_one.is_dir()
    assert not (skill_root / "demo-skill").exists()


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


def _write_claude_skill(skill_root: Path, name: str) -> None:
    skill_dir = skill_root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name}\n---\n",
        encoding="utf-8",
    )


def _apply_claude_pack(
    tmp_path: Path,
    *,
    pack_id: str,
    skill_name: str,
):
    from sos.apply import apply_write_plan
    from sos.cli import _annotate_backup_metadata
    from sos.planner import build_pack_apply_plan
    from sos.propose import PackProposal
    from sos.toml_io import read_toml

    skill_root = tmp_path / "skills"
    skill_root.mkdir(exist_ok=True)
    _write_claude_skill(skill_root, skill_name)
    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    plan = build_pack_apply_plan(
        runtime_paths,
        skill_root,
        codex_config_path,
        (PackProposal(pack_id=pack_id, skill_names=(skill_name,), reason="test"),),
        host="claude",
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
    assert apply_result.backup_id is not None
    _annotate_backup_metadata(
        runtime_paths,
        apply_result.backup_id,
        codex_config_path,
        skill_root,
        "claude",
    )
    metadata_path = runtime_paths.backups / apply_result.backup_id / "metadata.toml"
    return runtime_paths, skill_root, codex_config_path, apply_result.backup_id, read_toml(metadata_path)


def test_claude_backup_metadata_records_archive_restore_entries(tmp_path: Path):
    runtime_paths, skill_root, _, backup_id, metadata = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )

    assert metadata["host"] == "claude"
    assert metadata["vault_root"] == runtime_paths.vault.as_posix()
    assert metadata["active_skill_root"] == skill_root.as_posix()
    entries = metadata["archive_restore_entries"]
    assert entries == [
        {
            "pack_id": "demo",
            "skill_name": "demo-skill",
            "archive_path": (skill_root / ".sos-archive" / "demo" / "demo-skill").as_posix(),
            "source_path": (skill_root / "demo-skill").as_posix(),
        }
    ]
    assert "\\" not in metadata["vault_root"]
    assert "\\" not in metadata["active_skill_root"]
    assert "\\" not in entries[0]["archive_path"]
    assert "\\" not in entries[0]["source_path"]
    assert (runtime_paths.backups / backup_id / "metadata.toml").is_file()


def test_restore_claude_backup_uses_selected_backup_metadata_not_current_manifests(
    tmp_path: Path,
):
    runtime_paths, skill_root, codex_config_path, backup_a, _ = _apply_claude_pack(
        tmp_path,
        pack_id="alpha",
        skill_name="alpha-skill",
    )
    _, _, _, backup_b, _ = _apply_claude_pack(
        tmp_path,
        pack_id="beta",
        skill_name="beta-skill",
    )

    beta_archive = skill_root / ".sos-archive" / "beta" / "beta-skill"
    assert beta_archive.is_dir()
    assert backup_a != backup_b

    restore_backup(
        runtime_paths,
        backup_a,
        codex_config_path,
        runtime_paths.vault,
        apply=True,
    )

    assert (skill_root / "alpha-skill" / "SKILL.md").is_file()
    assert not (skill_root / ".sos-archive" / "alpha" / "alpha-skill").exists()
    assert beta_archive.is_dir()
    assert not (skill_root / "beta-skill").exists()


def test_restore_claude_rolls_archive_back_when_vault_restore_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Pre-create vault directory so the backup captures a vault snapshot
    vault_dir = tmp_path / "runtime" / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / "SKILL.md").write_text("# vault\n", encoding="utf-8")

    runtime_paths, skill_root, codex_config_path, backup_id, _ = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )

    original_replace_directory_atomic = backups._replace_directory_atomic

    def fail_vault_restore(source: Path, target: Path) -> None:
        if source == runtime_paths.backups / backup_id / "vault":
            raise RuntimeError("vault restore failed")
        original_replace_directory_atomic(source, target)

    monkeypatch.setattr(backups, "_replace_directory_atomic", fail_vault_restore)

    with pytest.raises(RuntimeError, match="vault restore failed"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )

    assert not (skill_root / "demo-skill").exists()
    assert (skill_root / ".sos-archive" / "demo" / "demo-skill" / "SKILL.md").is_file()


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


def test_restore_claude_legacy_backup_without_archive_entries_uses_manifest_fallback(
    tmp_path: Path,
):
    from sos.toml_io import read_toml

    runtime_paths, skill_root, codex_config_path, backup_id, _ = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )
    metadata_path = runtime_paths.backups / backup_id / "metadata.toml"
    metadata = read_toml(metadata_path)
    metadata.pop("archive_restore_entries")
    write_toml(metadata_path, metadata)

    restore_backup(
        runtime_paths,
        backup_id,
        codex_config_path,
        runtime_paths.vault,
        apply=True,
    )

    assert (skill_root / "demo-skill" / "SKILL.md").is_file()
    assert not (skill_root / ".sos-archive" / "demo" / "demo-skill").exists()


def test_restore_claude_rejects_metadata_source_path_that_does_not_match_expected(
    tmp_path: Path,
):
    from sos.toml_io import write_toml

    runtime_paths, skill_root, codex_config_path, backup_id, metadata = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )
    metadata_path = runtime_paths.backups / backup_id / "metadata.toml"

    # Test 1: Tamper source_path to point outside active skill root
    tampered_source = dict(metadata)
    entries = list(tampered_source["archive_restore_entries"])
    entries[0] = dict(entries[0])
    entries[0]["source_path"] = (tmp_path / "outside" / "evil").as_posix()
    tampered_source["archive_restore_entries"] = entries
    write_toml(metadata_path, tampered_source)

    with pytest.raises(ValueError, match="does not match expected"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )

    # Test 2: Tamper archive_path to point outside expected archive location
    tampered_archive = dict(metadata)
    entries2 = list(tampered_archive["archive_restore_entries"])
    entries2[0] = dict(entries2[0])
    entries2[0]["archive_path"] = (tmp_path / "outside" / "evil-archive").as_posix()
    tampered_archive["archive_restore_entries"] = entries2
    write_toml(metadata_path, tampered_archive)

    with pytest.raises(ValueError, match="does not match expected"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )


def test_restore_claude_rejects_when_target_already_exists(tmp_path: Path):
    runtime_paths, skill_root, codex_config_path, backup_id, _ = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )
    source_path = skill_root / "demo-skill"
    # Recreate the skill directory that was moved to archive
    source_path.mkdir(parents=True, exist_ok=True)
    (source_path / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: recreated\n---\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already exist"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )

    # The recreated directory must NOT be destroyed by the preflight
    assert source_path.is_dir()
    assert (source_path / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "---\nname: demo-skill\ndescription: recreated\n---\n"


def test_restore_claude_rollback_double_failure_shows_combined_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Pre-create vault directory so the backup captures a vault snapshot
    vault_dir = tmp_path / "runtime" / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / "SKILL.md").write_text("# vault\n", encoding="utf-8")

    runtime_paths, skill_root, codex_config_path, backup_id, _ = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )

    def fail_vault_restore(source: Path, target: Path) -> None:
        raise RuntimeError("vault restore failed")

    def fail_rollback(moves: tuple[tuple[Path, Path], ...]) -> None:
        raise RuntimeError("rollback failed")

    monkeypatch.setattr(backups, "_replace_directory_atomic", fail_vault_restore)
    monkeypatch.setattr(
        backups, "_rollback_restored_archive_moves", fail_rollback
    )

    with pytest.raises(RuntimeError) as exc_info:
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )

    msg = str(exc_info.value)
    assert "vault restore failed" in msg
    assert "rollback failed" in msg
