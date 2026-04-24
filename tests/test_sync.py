from pathlib import Path

import pytest

from sos.fingerprint import fingerprint_dir
from sos.manifest import load_pack_manifest, save_pack_manifest
from sos.models import OperationKind, PackManifest, SkillEntry
import sos.sync as sync
from sos.sync import activate_pack, apply_pack_sync, plan_pack_sync


def test_activate_ready_does_not_write(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Source\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Source\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    original_mtime = manifest_path.stat().st_mtime_ns

    result = activate_pack(manifest_path)

    assert result.status == "ready"
    assert result.operations == ()
    assert manifest_path.stat().st_mtime_ns == original_mtime


def test_activate_clean_source_drift_replaces_vault_and_updates_manifest_fingerprints(
    tmp_path: Path,
):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Original\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    (source / "SKILL.md").write_text("# Updated source\n", encoding="utf-8")
    expected_source_fingerprint = fingerprint_dir(source)

    result = activate_pack(manifest_path)

    assert result.status == "synced"
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Updated source\n"
    updated_manifest = load_pack_manifest(manifest_path)
    updated_skill = updated_manifest.skills[0]
    assert updated_skill.last_source_fingerprint == expected_source_fingerprint
    assert updated_skill.last_vault_fingerprint == fingerprint_dir(vault)
    assert updated_skill.last_source_fingerprint == updated_skill.last_vault_fingerprint
    assert tuple(operation.kind for operation in result.operations) == (
        OperationKind.COPY_SKILL,
        OperationKind.WRITE_MANIFEST,
    )


def test_activate_conflict_stops_without_overwriting(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original source\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Original vault\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    (source / "SKILL.md").write_text("# Updated source\n", encoding="utf-8")
    (vault / "SKILL.md").write_text("# Local vault edit\n", encoding="utf-8")

    result = activate_pack(manifest_path)

    assert result.status == "conflict"
    assert result.operations == ()
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Local vault edit\n"


def test_activate_stale_source_warns_and_keeps_vault(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Vault copy\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    _remove_skill(source)

    result = activate_pack(manifest_path)

    assert result.status == "stale-source"
    assert result.operations == ()
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Vault copy\n"
    assert any("missing" in message or "invalid" in message for message in result.messages)


def test_activate_never_modifies_codex_config(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Original\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("[skills]\n", encoding="utf-8")
    original_config_mtime = codex_config_path.stat().st_mtime_ns
    (source / "SKILL.md").write_text("# Updated source\n", encoding="utf-8")

    result = activate_pack(manifest_path)

    assert result.status == "synced"
    assert codex_config_path.stat().st_mtime_ns == original_config_mtime
    assert codex_config_path.read_text(encoding="utf-8") == "[skills]\n"


def test_explicit_pack_sync_apply_updates_vault_and_manifest_only(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Original\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("[skills]\n", encoding="utf-8")
    original_config_mtime = codex_config_path.stat().st_mtime_ns
    source_extra = source / "scripts" / "tool.py"
    source_extra.parent.mkdir(parents=True)
    source_extra.write_text("print('tool')\n", encoding="utf-8")

    sync_plan = plan_pack_sync(manifest_path)
    result = apply_pack_sync(sync_plan, apply=True)

    assert result.status == "synced"
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Original\n"
    assert (vault / "scripts" / "tool.py").read_text(encoding="utf-8") == "print('tool')\n"
    assert codex_config_path.stat().st_mtime_ns == original_config_mtime
    assert codex_config_path.read_text(encoding="utf-8") == "[skills]\n"
    assert source_extra.read_text(encoding="utf-8") == "print('tool')\n"
    updated_skill = load_pack_manifest(manifest_path).skills[0]
    assert updated_skill.last_source_fingerprint == fingerprint_dir(source)
    assert updated_skill.last_vault_fingerprint == fingerprint_dir(vault)
    assert tuple(operation.target for operation in result.operations) == (vault, manifest_path)


def test_malformed_vault_path_outside_vault_root_is_rejected_before_writes(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original\n")
    outside = _write_skill(tmp_path / "outside", "work-skill", "# Outside original\n")
    manifest_path = _write_manifest(
        tmp_path,
        source,
        outside,
        vault_root=tmp_path / "vault",
    )
    (source / "SKILL.md").write_text("# Updated source\n", encoding="utf-8")

    result = activate_pack(manifest_path)

    assert result.status == "conflict"
    assert result.operations == ()
    assert outside.parent == tmp_path / "outside"
    assert outside.joinpath("SKILL.md").read_text(encoding="utf-8") == "# Outside original\n"
    assert any("vault path" in message for message in result.messages)


def test_multi_skill_sync_rolls_back_first_copy_when_second_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_one = _write_skill(tmp_path / "source", "one", "# One original\n")
    source_two = _write_skill(tmp_path / "source", "two", "# Two original\n")
    vault_one = _write_skill(tmp_path / "vault", "one", "# One original\n")
    vault_two = _write_skill(tmp_path / "vault", "two", "# Two original\n")
    manifest_path = _write_manifest_for_skills(
        tmp_path,
        ((source_one, vault_one), (source_two, vault_two)),
    )
    original_manifest_text = manifest_path.read_text(encoding="utf-8")
    (source_one / "SKILL.md").write_text("# One updated\n", encoding="utf-8")
    (source_two / "SKILL.md").write_text("# Two updated\n", encoding="utf-8")
    original_replace = sync.replace_skill_folder_atomic
    calls: list[Path] = []

    def fail_second_copy(source: Path, target: Path) -> None:
        calls.append(target)
        if len(calls) == 2:
            raise RuntimeError("copy failed")
        original_replace(source, target)

    monkeypatch.setattr(sync, "replace_skill_folder_atomic", fail_second_copy)

    result = apply_pack_sync(plan_pack_sync(manifest_path), apply=True)

    assert result.status == "failed"
    assert "copy failed" in " ".join(result.messages)
    assert (vault_one / "SKILL.md").read_text(encoding="utf-8") == "# One original\n"
    assert (vault_two / "SKILL.md").read_text(encoding="utf-8") == "# Two original\n"
    assert manifest_path.read_text(encoding="utf-8") == original_manifest_text


def test_stale_and_conflict_in_same_pack_returns_conflict_without_sync(tmp_path: Path):
    stale_source = _write_skill(tmp_path / "source", "stale", "# Stale original\n")
    stale_vault = _write_skill(tmp_path / "vault", "stale", "# Stale original\n")
    conflict_source = _write_skill(tmp_path / "source", "conflict", "# Conflict original\n")
    conflict_vault = _write_skill(tmp_path / "vault", "conflict", "# Conflict original\n")
    clean_source = _write_skill(tmp_path / "source", "clean", "# Clean original\n")
    clean_vault = _write_skill(tmp_path / "vault", "clean", "# Clean original\n")
    manifest_path = _write_manifest_for_skills(
        tmp_path,
        (
            (stale_source, stale_vault),
            (conflict_source, conflict_vault),
            (clean_source, clean_vault),
        ),
    )
    _remove_skill(stale_source)
    (conflict_source / "SKILL.md").write_text("# Conflict source updated\n", encoding="utf-8")
    (conflict_vault / "SKILL.md").write_text("# Conflict vault updated\n", encoding="utf-8")
    (clean_source / "SKILL.md").write_text("# Clean source updated\n", encoding="utf-8")

    result = activate_pack(manifest_path)

    assert result.status == "conflict"
    assert result.operations == ()
    assert (clean_vault / "SKILL.md").read_text(encoding="utf-8") == "# Clean original\n"
    assert any("source and vault both changed" in message for message in result.messages)
    assert any("source missing or invalid" in message for message in result.messages)


def test_source_unchanged_vault_changed_returns_conflict_without_overwrite(tmp_path: Path):
    source = _write_skill(tmp_path / "source", "work-skill", "# Original\n")
    vault = _write_skill(tmp_path / "vault", "work-skill", "# Original\n")
    manifest_path = _write_manifest(tmp_path, source, vault)
    (vault / "SKILL.md").write_text("# Vault local edit\n", encoding="utf-8")

    result = activate_pack(manifest_path)

    assert result.status == "conflict"
    assert result.operations == ()
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Vault local edit\n"


def _write_skill(root: Path, name: str, skill_md: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return skill


def _write_manifest(
    tmp_path: Path,
    source: Path,
    vault: Path,
    vault_root: Path | None = None,
) -> Path:
    return _write_manifest_for_skills(
        tmp_path,
        ((source, vault),),
        vault_root=vault_root,
    )


def _write_manifest_for_skills(
    tmp_path: Path,
    skill_paths: tuple[tuple[Path, Path], ...],
    vault_root: Path | None = None,
) -> Path:
    manifest_path = tmp_path / "packs" / "work.toml"
    save_pack_manifest(
        manifest_path,
        PackManifest(
            id="work",
            display_name="Work",
            pointer_skill="sos-work",
            sync_policy="clean-auto",
            vault_root=vault_root or skill_paths[0][1].parent,
            skills=tuple(
                _skill_entry(source, vault) for source, vault in skill_paths
            ),
        ),
    )
    return manifest_path


def _skill_entry(source: Path, vault: Path) -> SkillEntry:
    return SkillEntry(
        name=source.name,
        source_path=source,
        vault_path=vault,
        origin="codex",
        last_source_fingerprint=fingerprint_dir(source),
        last_vault_fingerprint=fingerprint_dir(vault),
        last_synced_at="2026-04-24T15:28:00+08:00",
    )


def _remove_skill(skill: Path) -> None:
    for path in sorted(skill.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    skill.rmdir()
