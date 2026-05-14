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


def test_restore_legacy_workspace_activation_backup_without_host_restores_agents_tree(
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    agents_root = workspace_root / ".agents"
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    backup_id = "backup-20260424T120000000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    learned_snapshot = backup_dir / "learned-reference.md"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "LEGACY NAGATO\n",
        encoding="utf-8",
    )
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("LEGACY LEARNED\n", encoding="utf-8")
    write_toml(
        backup_dir / "metadata.toml",
        {
            "backup_id": backup_id,
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "legacy workspace activation",
            "scope": "workspace_activation",
            "workspace_root": str(workspace_root),
            "workspace_agents_target": str(agents_root),
            "workspace_agents_kind": "dir",
            "workspace_agents_snapshot_path": workspace_snapshot.as_posix(),
            "learned_reference_target": str(learned_target),
            "learned_reference_kind": "file",
            "learned_reference_snapshot_path": learned_snapshot.as_posix(),
        },
    )
    (agents_root / "skills" / "sos-nagato").mkdir(parents=True)
    (agents_root / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "CURRENT NAGATO\n",
        encoding="utf-8",
    )
    learned_target.parent.mkdir(parents=True)
    learned_target.write_text("CURRENT LEARNED\n", encoding="utf-8")

    restore_backup(
        runtime_paths,
        backup_id,
        codex_config_path=None,
        vault_root=None,
        apply=True,
    )

    assert (agents_root / "skills" / "sos-nagato" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "LEGACY NAGATO\n"
    assert learned_target.read_text(encoding="utf-8") == "LEGACY LEARNED\n"


def test_restore_workspace_activation_rejects_metadata_missing_target_keys(
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    backup_id = "backup-20260424T120000000000Z"
    backup_dir = runtime_paths.backups / backup_id
    backup_dir.mkdir(parents=True)
    write_toml(
        backup_dir / "metadata.toml",
        {
            "backup_id": backup_id,
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "corrupted",
            "scope": "workspace_activation",
            "workspace_root": str(workspace_root),
            # Intentionally missing workspace_skill_parent_target AND workspace_agents_target
            "workspace_skill_parent_kind": "missing",
            "learned_reference_target": str(
                runtime_paths.state / "recommendations" / "asahina-reference.md"
            ),
            "learned_reference_kind": "missing",
        },
    )

    with pytest.raises(ValueError, match="missing workspace_skill_parent_target"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path=None,
            vault_root=None,
            apply=True,
        )


def test_restore_workspace_activation_rejects_missing_learned_reference_kind_before_writing(
    tmp_path: Path,
):
    """Missing learned_reference_kind must fail before touching workspace files."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("SHOULD SURVIVE\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    backup_id = "backup-20260514T120000000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "SNAPSHOT\n", encoding="utf-8"
    )
    learned_snapshot = backup_dir / "learned-reference.md"
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("SNAPSHOT LEARNED\n", encoding="utf-8")
    metadata = {
        "backup_id": backup_id,
        "created_at": "2026-05-14T12:00:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        "learned_reference_target": str(learned_target),
        # Intentionally OMITTING learned_reference_kind
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    }
    write_toml(backup_dir / "metadata.toml", metadata)

    with pytest.raises(ValueError, match="learned_reference_kind"):
        restore_backup(
            runtime_paths, backup_id,
            codex_config_path=None, vault_root=None, apply=True,
        )

    assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "SHOULD SURVIVE\n"


def test_restore_workspace_activation_rejects_missing_snapshot_for_dir_kind_before_writing(
    tmp_path: Path,
):
    """kind=dir but snapshot path points to nonexistent dir must fail before writes."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("SHOULD SURVIVE\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    backup_id = "backup-20260514T120100000000Z"
    backup_dir = runtime_paths.backups / backup_id
    # Intentionally do NOT create the workspace-agents snapshot directory
    metadata = {
        "backup_id": backup_id,
        "created_at": "2026-05-14T12:01:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": (backup_dir / "workspace-agents").as_posix(),
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "missing",
    }
    write_toml(backup_dir / "metadata.toml", metadata)

    with pytest.raises(ValueError, match="snapshot"):
        restore_backup(
            runtime_paths, backup_id,
            codex_config_path=None, vault_root=None, apply=True,
        )

    assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "SHOULD SURVIVE\n"


def test_restore_workspace_activation_rolls_back_skill_parent_on_learned_reference_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """If learned reference restore fails after skill parent restore, skill parent must be rolled back."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("CURRENT NAGATO\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    learned_target.parent.mkdir(parents=True)
    learned_target.write_text("CURRENT LEARNED\n", encoding="utf-8")
    backup_id = "backup-20260514T120200000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "SNAPSHOT NAGATO\n", encoding="utf-8"
    )
    learned_snapshot = backup_dir / "learned-reference.md"
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("SNAPSHOT LEARNED\n", encoding="utf-8")
    write_toml(backup_dir / "metadata.toml", {
        "backup_id": backup_id,
        "created_at": "2026-05-14T12:02:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "file",
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    })

    original_replace_file_atomic = backups._replace_file_atomic

    def fail_learned_restore(source: Path, target: Path) -> None:
        if target == learned_target:
            raise RuntimeError("learned reference restore failed")
        original_replace_file_atomic(source, target)

    monkeypatch.setattr(backups, "_replace_file_atomic", fail_learned_restore)

    with pytest.raises(RuntimeError, match="learned reference restore failed"):
        restore_backup(
            runtime_paths, backup_id,
            codex_config_path=None, vault_root=None, apply=True,
        )

    # Skill parent must be rolled back to its pre-restore state
    assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "CURRENT NAGATO\n"


def test_restore_workspace_activation_rolls_back_both_targets_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """If learned reference restore fails after skill parent restore, BOTH must be rolled back."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("ORIGINAL SP\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    learned_target.parent.mkdir(parents=True)
    learned_target.write_text("ORIGINAL LR\n", encoding="utf-8")
    backup_id = "backup-20260515T110000000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "BACKUP SP\n", encoding="utf-8"
    )
    learned_snapshot = backup_dir / "learned-reference.md"
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("BACKUP LR\n", encoding="utf-8")
    write_toml(backup_dir / "metadata.toml", {
        "backup_id": backup_id,
        "created_at": "2026-05-15T11:00:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "file",
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    })

    # Monkeypatch _restore_snapshot_by_kind to corrupt the learned reference target
    # before raising during the initial restore (not rollback). Rollback calls use
    # pre-restore snapshot paths under a temp dir, while initial restore uses backup paths.
    original_restore_snapshot = backups._restore_snapshot_by_kind
    restore_calls = {"count": 0}

    def fail_on_learned_reference(*, kind, snapshot_path, target):
        restore_calls["count"] += 1
        # Only fail on the initial restore (1st call for learned reference target).
        # Rollback calls will have a different snapshot_path (under temp dir).
        if target == learned_target and restore_calls["count"] == 2:
            # Simulate partial write: corrupt the target before failing
            target.write_text("CORRUPTED PARTIAL\n", encoding="utf-8")
            raise RuntimeError("learned reference restore failed")
        original_restore_snapshot(kind=kind, snapshot_path=snapshot_path, target=target)

    monkeypatch.setattr(backups, "_restore_snapshot_by_kind", fail_on_learned_reference)

    with pytest.raises(RuntimeError, match="learned reference restore failed"):
        restore_backup(
            runtime_paths, backup_id,
            codex_config_path=None, vault_root=None, apply=True,
        )

    # Skill parent must be rolled back to its pre-restore state
    assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "ORIGINAL SP\n"
    # Learned reference must also be rolled back to its pre-restore state (not CORRUPTED PARTIAL)
    assert learned_target.read_text(encoding="utf-8") == "ORIGINAL LR\n"


def test_restore_workspace_activation_rollback_double_failure_shows_combined_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """If learned reference restore fails AND rollback also fails, show combined error."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("CURRENT NAGATO\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    learned_target.parent.mkdir(parents=True)
    learned_target.write_text("CURRENT LEARNED\n", encoding="utf-8")
    backup_id = "backup-20260514T120400000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "SNAPSHOT NAGATO\n", encoding="utf-8"
    )
    learned_snapshot = backup_dir / "learned-reference.md"
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("SNAPSHOT LEARNED\n", encoding="utf-8")
    write_toml(backup_dir / "metadata.toml", {
        "backup_id": backup_id,
        "created_at": "2026-05-14T12:04:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "file",
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    })

    original_replace_file_atomic = backups._replace_file_atomic
    original_replace_directory_atomic = backups._replace_directory_atomic
    dir_restore_calls = {"count": 0}

    def fail_learned_restore(source: Path, target: Path) -> None:
        """Succeed for all file restores except learned reference target."""
        if target == learned_target:
            raise RuntimeError("learned reference restore failed")
        original_replace_file_atomic(source, target)

    def allow_first_dir_restore_then_fail(source: Path, target: Path) -> None:
        """Allow the initial skill parent restore, then fail on rollback."""
        dir_restore_calls["count"] += 1
        if dir_restore_calls["count"] == 1:
            original_replace_directory_atomic(source, target)
        else:
            raise RuntimeError("rollback directory failed")

    monkeypatch.setattr(backups, "_replace_file_atomic", fail_learned_restore)
    monkeypatch.setattr(backups, "_replace_directory_atomic", allow_first_dir_restore_then_fail)

    with pytest.raises(RuntimeError) as exc_info:
        restore_backup(
            runtime_paths, backup_id,
            codex_config_path=None, vault_root=None, apply=True,
        )

    msg = str(exc_info.value).lower()
    assert "workspace activation restore failed" in msg
    # At least one rollback error must be reported with a specific prefix
    assert "learned reference rollback" in msg or "skill parent rollback" in msg


def test_restore_workspace_activation_rejects_wrong_workspace_skill_root_before_writing(
    tmp_path: Path,
):
    """workspace_skill_root pointing to wrong workspace must fail before writes."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    other_root = tmp_path / "other-workspace"
    other_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("SHOULD SURVIVE\n", encoding="utf-8")
    backup_id = "backup-20260514T120300000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "SNAPSHOT\n", encoding="utf-8"
    )
    write_toml(backup_dir / "metadata.toml", {
        "backup_id": backup_id,
        "created_at": "2026-05-14T12:03:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        # Wrong: workspace_skill_root points to other workspace
        "workspace_skill_root": str(other_root / ".agents" / "skills"),
        "learned_reference_target": str(
            runtime_paths.state / "recommendations" / "asahina-reference.md"
        ),
        "learned_reference_kind": "missing",
    })

    with pytest.raises(ValueError, match="workspace_skill_root"):
        restore_backup(
            runtime_paths, backup_id,
            codex_config_path=None, vault_root=None, apply=True,
        )

    assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "SHOULD SURVIVE\n"


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


@pytest.mark.parametrize(
    "backup_id",
    ("a:b", "CON.txt", "LPT1.md", "NUL.skill", "x.", "x "),
)
def test_validate_backup_id_component_rejects_windows_unsafe_names(backup_id: str):
    with pytest.raises(ValueError, match="unsafe backup_id"):
        backups._validate_backup_id_component(backup_id)


def test_restore_backup_rejects_windows_unsafe_backup_id_before_lookup(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")

    with pytest.raises(ValueError, match="unsafe backup_id"):
        restore_backup(
            runtime_paths,
            "CON.txt",
            codex_config_path=None,
            vault_root=None,
            apply=False,
        )


def test_validate_metadata_backup_id_rejects_windows_unsafe_name_without_filesystem_path():
    with pytest.raises(ValueError, match="unsafe backup_id"):
        backups._validate_metadata_backup_id(
            "CON.txt",
            Path("CON.txt") / "metadata.toml",
        )


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


def test_legacy_restore_rejects_target_collisions(tmp_path: Path):
    from sos.toml_io import read_toml, write_toml

    # Set up two packs whose skills have source_paths colliding by casefold.
    # Use _apply_claude_pack for each, then remove archive_restore_entries
    # to force the legacy manifest fallback.

    # Pack A: creates archive at .../pack-a/demo-skill, source = skills/demo-skill
    runtime_paths, skill_root, codex_config_path, backup_a, meta_a = _apply_claude_pack(
        tmp_path,
        pack_id="pack-a",
        skill_name="demo-skill",
    )
    # Pack B: creates archive at .../pack-b/DEMO-SKILL, source = skills/DEMO-SKILL
    # source_path casefolds to same as demo-skill → collision
    _, _, _, backup_b, meta_b = _apply_claude_pack(
        tmp_path,
        pack_id="pack-b",
        skill_name="DEMO-SKILL",
    )

    # Use backup B's metadata but strip archive_restore_entries to force
    # legacy fallback (reads both pack manifests from runtime_paths.packs)
    meta_b.pop("archive_restore_entries")
    write_toml(
        runtime_paths.backups / backup_b / "metadata.toml",
        meta_b,
    )

    with pytest.raises(ValueError, match="collision"):
        restore_backup(
            runtime_paths,
            backup_b,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )


def test_restore_rejects_relative_active_skill_root(tmp_path: Path):
    """Tampered metadata with a relative active_skill_root must be rejected."""
    from sos.toml_io import read_toml, write_toml

    runtime_paths, skill_root, codex_config_path, backup_id, metadata = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )

    tampered = dict(metadata)
    tampered["active_skill_root"] = "skills"
    write_toml(runtime_paths.backups / backup_id / "metadata.toml", tampered)

    with pytest.raises(ValueError, match="must be absolute"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )


def test_restore_rejects_broken_symlink_at_target(tmp_path: Path):
    """A broken symlink at the restore target must be treated as conflicting."""
    runtime_paths, skill_root, codex_config_path, backup_id, _ = _apply_claude_pack(
        tmp_path,
        pack_id="demo",
        skill_name="demo-skill",
    )
    source_path = skill_root / "demo-skill"
    # After apply, source_path is moved to archive; create a broken symlink there
    assert not source_path.exists()
    assert not source_path.is_symlink()
    try:
        source_path.symlink_to("/nonexistent")
    except FileExistsError:
        raise
    except (OSError, NotImplementedError):
        if source_path.exists() or source_path.is_symlink():
            raise
        pytest.skip("symlink creation unavailable")
    assert source_path.is_symlink()
    assert not source_path.exists()

    with pytest.raises(ValueError, match="already exist"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path,
            runtime_paths.vault,
            apply=True,
        )

    # The broken symlink must survive the preflight
    assert source_path.is_symlink()


def test_workspace_activation_backup_metadata_stores_absolute_paths(tmp_path: Path):
    """create_workspace_activation_backup must store absolute paths even when
    called with relative workspace_root."""
    import os
    from sos.backups import create_workspace_activation_backup
    from sos.toml_io import read_toml

    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    learned_target.parent.mkdir(parents=True, exist_ok=True)
    learned_target.write_text("learned\n", encoding="utf-8")

    # Use a relative-style path to simulate caller passing "./workspace"
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        relative_workspace = Path("./workspace")
        record = create_workspace_activation_backup(
            runtime_paths,
            workspace_root=relative_workspace,
            workspace_skill_parent_root=workspace_root / ".agents",
            learned_reference_target=learned_target,
            reason="test relative paths",
            host="codex",
        )
    finally:
        os.chdir(original_cwd)

    # Read the metadata TOML directly
    metadata_path = runtime_paths.backups / record.backup_id / "metadata.toml"
    metadata = read_toml(metadata_path)

    # All path values must be absolute POSIX paths (no relative segments like ./  or ..)
    for key in (
        "workspace_root",
        "workspace_skill_parent_target",
        "workspace_skill_root",
        "learned_reference_target",
    ):
        value = metadata[key]
        assert not value.startswith("./"), f"{key} should be absolute, got: {value}"
        assert not value.startswith(".."), f"{key} should be absolute, got: {value}"
        assert Path(value).is_absolute(), f"{key} should be absolute, got: {value}"


def test_restore_workspace_activation_with_relative_workspace_root_in_metadata_cross_cwd(
    tmp_path: Path,
):
    """Restoring from metadata that contains relative workspace paths must
    resolve them correctly regardless of cwd, and must NOT write to a wrong
    directory relative to the current cwd."""
    import os
    from sos.backups import restore_backup
    from sos.toml_io import write_toml

    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("REAL CONTENT\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    learned_target.parent.mkdir(parents=True, exist_ok=True)
    learned_target.write_text("REAL LEARNED\n", encoding="utf-8")

    # Create a valid backup directory with snapshots
    backup_id = "backup-20260515T120000000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "SNAPSHOT CONTENT\n", encoding="utf-8"
    )
    learned_snapshot = backup_dir / "learned-reference.md"
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("SNAPSHOT LEARNED\n", encoding="utf-8")

    # Simulate metadata written by an older version that stored relative paths.
    # Write relative paths that are correct when resolved from tmp_path.
    write_toml(backup_dir / "metadata.toml", {
        "backup_id": backup_id,
        "created_at": "2026-05-15T12:00:00+00:00",
        "reason": "simulated old-format relative paths",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": "workspace",
        "workspace_skill_parent_target": "workspace/.agents",
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        "workspace_skill_root": "workspace/.agents/skills",
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "file",
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    })

    # Change cwd to a different directory to simulate cross-cwd restore
    other_dir = tmp_path / "other-cwd"
    other_dir.mkdir()
    original_cwd = os.getcwd()
    try:
        os.chdir(other_dir)
        # The restore should either:
        #  1. Resolve the relative paths and work correctly, OR
        #  2. Reject the restore (validation error)
        # It must NOT silently write to wrong_paths = other_dir / "workspace" / ".agents"
        try:
            restore_backup(
                runtime_paths,
                backup_id,
                codex_config_path=None,
                vault_root=None,
                apply=True,
            )
            # If restore succeeded, it must have written to the correct location
            assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "SNAPSHOT CONTENT\n"
            assert learned_target.read_text(encoding="utf-8") == "SNAPSHOT LEARNED\n"
        except ValueError:
            # Rejection is also acceptable -- the paths can't be validated
            pass
    finally:
        os.chdir(original_cwd)

    # Regardless of outcome, nothing should have been created in the wrong directory
    wrong_agents = other_dir / "workspace" / ".agents"
    assert not wrong_agents.exists(), (
        "Restore must not create files in a wrong directory relative to cwd"
    )


def test_replace_directory_atomic_handles_file_target(tmp_path: Path):
    """When the target is a file (not a directory), _replace_directory_atomic
    must still replace it with the source directory and clean up correctly."""
    from sos.backups import _replace_directory_atomic

    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Source Content\n", encoding="utf-8")

    target = tmp_path / "target"
    target.write_text("I am a file, not a directory\n", encoding="utf-8")

    _replace_directory_atomic(source, target)

    # target must now be a directory containing the source's content
    assert target.is_dir()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "# Source Content\n"
    # No stale backup artifacts left behind
    assert not any(p.suffix == ".bak" for p in tmp_path.iterdir())


def test_restore_workspace_activation_rejects_snapshot_path_outside_backup_dir(
    tmp_path: Path,
):
    """Tampered metadata pointing snapshot at external path must be rejected."""
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    agents_root = workspace_root / ".agents"
    agents_skill = agents_root / "skills" / "sos-nagato"
    agents_skill.mkdir(parents=True)
    (agents_skill / "SKILL.md").write_text("ORIGINAL CONTENT\n", encoding="utf-8")
    learned_target = runtime_paths.state / "recommendations" / "asahina-reference.md"
    learned_target.parent.mkdir(parents=True, exist_ok=True)
    learned_target.write_text("ORIGINAL LEARNED\n", encoding="utf-8")

    # Create a valid backup with real snapshots
    backup_id = "backup-20260515T130000000000Z"
    backup_dir = runtime_paths.backups / backup_id
    workspace_snapshot = backup_dir / "workspace-agents"
    (workspace_snapshot / "skills" / "sos-nagato").mkdir(parents=True)
    (workspace_snapshot / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "SNAPSHOT CONTENT\n", encoding="utf-8"
    )
    learned_snapshot = backup_dir / "learned-reference.md"
    learned_snapshot.parent.mkdir(parents=True, exist_ok=True)
    learned_snapshot.write_text("SNAPSHOT LEARNED\n", encoding="utf-8")
    write_toml(backup_dir / "metadata.toml", {
        "backup_id": backup_id,
        "created_at": "2026-05-15T13:00:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": workspace_snapshot.as_posix(),
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "file",
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    })

    # Create an external file outside the backup directory
    external_dir = tmp_path / "external-evil"
    external_dir.mkdir()
    external_file = external_dir / "workspace-agents"
    (external_file / "skills" / "sos-nagato").mkdir(parents=True)
    (external_file / "skills" / "sos-nagato" / "SKILL.md").write_text(
        "EVIL CONTENT\n", encoding="utf-8"
    )

    # Tamper metadata to point snapshot path at the external location
    tampered_metadata = {
        "backup_id": backup_id,
        "created_at": "2026-05-15T13:00:00+00:00",
        "reason": "test",
        "scope": "workspace_activation",
        "host": "codex",
        "workspace_root": str(workspace_root),
        "workspace_skill_parent_target": str(agents_root),
        "workspace_skill_parent_kind": "dir",
        "workspace_skill_parent_snapshot_path": external_file.as_posix(),
        "learned_reference_target": str(learned_target),
        "learned_reference_kind": "file",
        "learned_reference_snapshot_path": learned_snapshot.as_posix(),
    }
    write_toml(backup_dir / "metadata.toml", tampered_metadata)

    with pytest.raises(ValueError, match="escapes backup directory"):
        restore_backup(
            runtime_paths,
            backup_id,
            codex_config_path=None,
            vault_root=None,
            apply=True,
        )

    # Workspace must NOT have been modified
    assert (agents_skill / "SKILL.md").read_text(encoding="utf-8") == "ORIGINAL CONTENT\n"
    assert learned_target.read_text(encoding="utf-8") == "ORIGINAL LEARNED\n"
