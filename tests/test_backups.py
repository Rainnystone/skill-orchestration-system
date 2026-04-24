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
    assert record.metadata["config_snapshot_path"] == str(record.config_path)
    assert record.vault_path is not None
    assert (record.vault_path / "SKILL.md").read_text(encoding="utf-8") == "# Original\n"
    assert record.metadata["vault_snapshot_path"] == str(record.vault_path)


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
