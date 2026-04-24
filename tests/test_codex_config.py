from pathlib import Path

import pytest

import sos.codex_config as codex_config
from sos.codex_config import disable_skill_paths_with_backup, plan_disable_skill_paths
from sos.toml_io import read_toml


def test_plan_disable_skill_paths_preserves_existing_config():
    config = {"model": "gpt-5.5"}

    planned = plan_disable_skill_paths(config, ("/skills/apify/SKILL.md",))

    assert config == {"model": "gpt-5.5"}
    assert planned["model"] == "gpt-5.5"
    assert planned["skills"]["config"] == [
        {"path": "/skills/apify/SKILL.md", "enabled": False}
    ]


def test_plan_disable_skill_paths_disables_duplicate_existing_path_entries():
    config = {
        "skills": {
            "config": [
                {"path": "/skills/apify/SKILL.md", "enabled": True, "reason": "first"},
                {"path": "/skills/other/SKILL.md", "enabled": True},
                {"path": "/skills/apify/SKILL.md", "enabled": True, "reason": "duplicate"},
            ]
        }
    }

    planned = plan_disable_skill_paths(config, ("/skills/apify/SKILL.md",))

    assert planned["skills"]["config"] == [
        {"path": "/skills/apify/SKILL.md", "enabled": False, "reason": "first"},
        {"path": "/skills/other/SKILL.md", "enabled": True},
        {"path": "/skills/apify/SKILL.md", "enabled": False, "reason": "duplicate"},
    ]


def test_apply_disable_skill_paths_requires_backup_id(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.5"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="backup"):
        disable_skill_paths_with_backup(
            config_path,
            ("/skills/apify/SKILL.md",),
            backup_path=None,
            apply=True,
        )


def test_disable_skill_paths_apply_false_returns_plan_without_writing(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    original_text = 'model = "gpt-5.5"\n'
    config_path.write_text(original_text, encoding="utf-8")
    backup_path = tmp_path / "backups" / "backup-001" / "config.toml"

    planned = disable_skill_paths_with_backup(
        config_path,
        ("/skills/apify/SKILL.md",),
        backup_path=None,
        apply=False,
    )

    assert planned["skills"]["config"] == [
        {"path": "/skills/apify/SKILL.md", "enabled": False}
    ]
    assert config_path.read_text(encoding="utf-8") == original_text
    assert not backup_path.exists()


def test_apply_disable_skill_paths_writes_atomically_and_reparses(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    original_text = 'model = "gpt-5.5"\n'
    config_path.write_text(original_text, encoding="utf-8")
    backup_path = tmp_path / "backups" / "backup-001" / "config.toml"

    planned = disable_skill_paths_with_backup(
        config_path,
        ("/skills/apify/SKILL.md",),
        backup_path=backup_path,
        apply=True,
    )

    assert planned["model"] == "gpt-5.5"
    assert backup_path.read_text(encoding="utf-8") == original_text
    written = read_toml(config_path)
    assert written["model"] == "gpt-5.5"
    assert written["skills"]["config"] == [
        {"path": "/skills/apify/SKILL.md", "enabled": False}
    ]


def test_apply_disable_skill_paths_restores_original_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_path = tmp_path / "config.toml"
    original_text = 'model = "gpt-5.5"\n'
    config_path.write_text(original_text, encoding="utf-8")
    backup_path = tmp_path / "backups" / "backup-001" / "config.toml"

    def fail_atomic_write(path: str | Path, text: str) -> None:
        Path(path).write_text("partial write\n", encoding="utf-8")
        raise RuntimeError("write failed")

    monkeypatch.setattr(codex_config, "atomic_write_text", fail_atomic_write)

    with pytest.raises(RuntimeError, match="write failed"):
        disable_skill_paths_with_backup(
            config_path,
            ("/skills/apify/SKILL.md",),
            backup_path=backup_path,
            apply=True,
        )

    assert config_path.read_text(encoding="utf-8") == original_text


def test_apply_disable_skill_paths_restores_original_on_reparse_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_path = tmp_path / "config.toml"
    original_text = 'model = "gpt-5.5"\n'
    config_path.write_text(original_text, encoding="utf-8")
    backup_path = tmp_path / "backups" / "backup-001" / "config.toml"
    call_count = 0

    def fail_reparse_after_load(path: str | Path) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return read_toml(path)
        raise RuntimeError("reparse failed")

    monkeypatch.setattr(codex_config, "read_toml", fail_reparse_after_load)

    with pytest.raises(RuntimeError, match="reparse failed"):
        disable_skill_paths_with_backup(
            config_path,
            ("/skills/apify/SKILL.md",),
            backup_path=backup_path,
            apply=True,
        )

    assert call_count == 2
    assert config_path.read_text(encoding="utf-8") == original_text
