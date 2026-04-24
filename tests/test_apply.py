from pathlib import Path

import pytest

import sos.apply as apply_module
import sos.codex_config as codex_config
from sos.apply import apply_write_plan
from sos.models import OperationKind, WriteOperation, WritePlan
from sos.paths import RuntimePaths
from sos.planner import build_pack_apply_plan, load_write_plan, serialize_write_plan
from sos.propose import PackProposal
from sos.toml_io import read_toml, write_toml


def test_apply_requires_apply_true_for_external_writes(tmp_path: Path):
    active_root = tmp_path / "active"
    _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=False,
    )

    assert result.status == "planned"
    assert result.operations == plan.operations
    assert result.backup_id is None
    assert not runtime_paths.vault.exists()
    assert not runtime_paths.packs.exists()
    assert not runtime_paths.state.exists()
    assert not runtime_paths.backups.exists()
    assert not (active_root / "sos-haruhi").exists()
    assert not (active_root / "sos-apify").exists()
    assert not codex_config_path.exists()


def test_apply_executes_backup_copy_manifest_registry_pointer_and_config_disable(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
    )

    assert result.status == "applied"
    assert result.backup_id is not None
    backup_dir = runtime_paths.backups / result.backup_id
    assert (backup_dir / "metadata.toml").is_file()
    assert (backup_dir / "config.toml").is_file()
    assert (runtime_paths.vault / "apify" / "apify-actor-development" / "SKILL.md").is_file()
    assert read_toml(runtime_paths.packs / "apify.toml")["id"] == "apify"
    registry = read_toml(runtime_paths.state / "registry.toml")
    assert registry["active_pointers"] == ["sos-haruhi", "sos-apify"]
    assert (active_root / "sos-haruhi" / "SKILL.md").is_file()
    assert (active_root / "sos-apify" / "SKILL.md").is_file()

    disabled_entries = read_toml(codex_config_path)["skills"]["config"]
    assert disabled_entries == [{"path": str(source / "SKILL.md"), "enabled": False}]


def test_apply_preserves_source_folders_by_default(tmp_path: Path):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
    )

    assert result.status == "applied"
    assert (source / "SKILL.md").is_file()


def test_apply_rolls_back_config_when_config_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    original_config_text = codex_config_path.read_text(encoding="utf-8")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    def fail_atomic_write(path: str | Path, text: str) -> None:
        Path(path).write_text("partial write\n", encoding="utf-8")
        raise RuntimeError("write failed")

    monkeypatch.setattr(codex_config, "atomic_write_text", fail_atomic_write)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
    )

    assert result.status == "failed"
    assert "write failed" in result.message
    assert codex_config_path.read_text(encoding="utf-8") == original_config_text
    assert not (runtime_paths.vault / "apify" / "apify-actor-development").exists()
    assert not (runtime_paths.packs / "apify.toml").exists()
    assert not (runtime_paths.state / "registry.toml").exists()
    assert not (active_root / "sos-haruhi").exists()
    assert not (active_root / "sos-apify").exists()
    assert (source / "SKILL.md").is_file()


def test_apply_restores_preexisting_writes_when_config_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    original_config_text = codex_config_path.read_text(encoding="utf-8")
    preexisting_vault = runtime_paths.vault / "apify" / "apify-actor-development"
    preexisting_vault.mkdir(parents=True)
    (preexisting_vault / "SKILL.md").write_text("old vault\n", encoding="utf-8")
    preexisting_manifest = runtime_paths.packs / "apify.toml"
    write_toml(preexisting_manifest, {"id": "old-apify"})
    preexisting_registry = runtime_paths.state / "registry.toml"
    write_toml(preexisting_registry, {"active_pointers": ["old-pointer"]})
    preexisting_haruhi = active_root / "sos-haruhi" / "SKILL.md"
    preexisting_haruhi.parent.mkdir(parents=True)
    preexisting_haruhi.write_text("old haruhi\n", encoding="utf-8")
    preexisting_apify = active_root / "sos-apify" / "SKILL.md"
    preexisting_apify.parent.mkdir(parents=True)
    preexisting_apify.write_text("old apify\n", encoding="utf-8")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    def fail_atomic_write(path: str | Path, text: str) -> None:
        Path(path).write_text("partial write\n", encoding="utf-8")
        raise RuntimeError("write failed")

    monkeypatch.setattr(codex_config, "atomic_write_text", fail_atomic_write)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
    )

    assert result.status == "failed"
    assert "write failed" in result.message
    assert codex_config_path.read_text(encoding="utf-8") == original_config_text
    assert (preexisting_vault / "SKILL.md").read_text(encoding="utf-8") == "old vault\n"
    assert read_toml(preexisting_manifest) == {"id": "old-apify"}
    assert read_toml(preexisting_registry) == {"active_pointers": ["old-pointer"]}
    assert preexisting_haruhi.read_text(encoding="utf-8") == "old haruhi\n"
    assert preexisting_apify.read_text(encoding="utf-8") == "old apify\n"
    assert (source / "SKILL.md").is_file()


def test_apply_does_not_delete_source_without_delete_flags(tmp_path: Path):
    active_root = tmp_path / "active"
    apify_source = _write_skill(active_root, "apify-actor-development")
    obsidian_source = _write_skill(active_root, "obsidian-cli")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, apify_source / "SKILL.md", obsidian_source / "SKILL.md")
    plan = build_pack_apply_plan(
        runtime_paths,
        active_root,
        codex_config_path,
        (
            PackProposal(
                pack_id="apify",
                skill_names=("apify-actor-development",),
                reason="Apify skill family.",
            ),
            PackProposal(
                pack_id="obsidian",
                skill_names=("obsidian-cli",),
                reason="Obsidian skill family.",
            ),
        ),
    )

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
    )

    assert result.status == "applied"
    assert (apify_source / "SKILL.md").is_file()
    assert (obsidian_source / "SKILL.md").is_file()


def test_delete_source_refuses_plugin_cache_paths(tmp_path: Path):
    active_root = tmp_path / ".codex" / "plugins" / "cache"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    with pytest.raises(ValueError, match="plugin cache"):
        apply_write_plan(
            plan,
            runtime_paths,
            codex_config_path,
            active_root,
            apply=True,
            delete_source=True,
            confirm_delete_source="apify",
        )

    assert (source / "SKILL.md").is_file()
    assert not runtime_paths.backups.exists()


def test_delete_source_refuses_claude_specific_paths_unless_explicitly_selected(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    claude_source = _write_skill(active_root / ".claude" / "skills", "claude-only")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    with pytest.raises(ValueError, match="Claude-specific"):
        apply_write_plan(
            plan,
            runtime_paths,
            codex_config_path,
            active_root,
            apply=True,
            delete_source=True,
            confirm_delete_source="apify",
            delete_source_paths=(active_root / ".claude",),
        )

    assert (source / "SKILL.md").is_file()
    assert (claude_source / "SKILL.md").is_file()
    assert not runtime_paths.backups.exists()


def test_delete_source_refuses_claude_specific_candidate_without_exact_selection(
    tmp_path: Path,
):
    active_root = tmp_path / ".claude" / "skills"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    with pytest.raises(ValueError, match="Claude-specific"):
        apply_write_plan(
            plan,
            runtime_paths,
            codex_config_path,
            active_root,
            apply=True,
            delete_source=True,
            confirm_delete_source="apify",
        )

    assert (source / "SKILL.md").is_file()
    assert not runtime_paths.backups.exists()


def test_delete_source_allows_exact_claude_specific_candidate_selection(
    tmp_path: Path,
):
    active_root = tmp_path / ".claude" / "skills"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
        delete_source=True,
        confirm_delete_source="apify",
        delete_source_paths=(source,),
    )

    assert result.status == "applied"
    assert result.deleted_source_paths == (source,)
    assert not source.exists()


def test_delete_source_refuses_paths_not_present_in_write_plan(tmp_path: Path):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    outside_candidate = _write_skill(active_root, "not-in-plan")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)

    with pytest.raises(ValueError, match="write plan deletion candidates"):
        apply_write_plan(
            plan,
            runtime_paths,
            codex_config_path,
            active_root,
            apply=True,
            delete_source=True,
            confirm_delete_source="apify",
            delete_source_paths=(outside_candidate,),
        )

    assert (source / "SKILL.md").is_file()
    assert (outside_candidate / "SKILL.md").is_file()
    assert not runtime_paths.backups.exists()


def test_delete_source_failure_restores_deleted_sources_and_apply_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    active_root = tmp_path / "active"
    first_source = _write_skill(active_root, "apify-actor-development")
    second_source = _write_skill(active_root, "apify-ecommerce")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, first_source / "SKILL.md", second_source / "SKILL.md")
    original_config_text = codex_config_path.read_text(encoding="utf-8")
    preexisting_vault = runtime_paths.vault / "apify" / "apify-actor-development"
    preexisting_vault.mkdir(parents=True)
    (preexisting_vault / "SKILL.md").write_text("old vault\n", encoding="utf-8")
    preexisting_manifest = runtime_paths.packs / "apify.toml"
    write_toml(preexisting_manifest, {"id": "old-apify"})
    plan = build_pack_apply_plan(
        runtime_paths,
        active_root,
        codex_config_path,
        (
            PackProposal(
                pack_id="apify",
                skill_names=("apify-actor-development", "apify-ecommerce"),
                reason="Apify skill family.",
            ),
        ),
    )
    original_rmtree = apply_module.shutil.rmtree
    failure_triggered = False

    def fail_second_source_once(path: str | Path, *args, **kwargs) -> None:
        nonlocal failure_triggered
        if Path(path) == second_source and not failure_triggered:
            failure_triggered = True
            raise RuntimeError("delete failed")
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(apply_module.shutil, "rmtree", fail_second_source_once)

    result = apply_write_plan(
        plan,
        runtime_paths,
        codex_config_path,
        active_root,
        apply=True,
        delete_source=True,
        confirm_delete_source="apify",
    )

    assert result.status == "failed"
    assert "delete failed" in result.message
    assert (first_source / "SKILL.md").is_file()
    assert (second_source / "SKILL.md").is_file()
    assert codex_config_path.read_text(encoding="utf-8") == original_config_text
    assert (preexisting_vault / "SKILL.md").read_text(encoding="utf-8") == "old vault\n"
    assert read_toml(preexisting_manifest) == {"id": "old-apify"}
    assert not (runtime_paths.vault / "apify" / "apify-ecommerce").exists()
    assert not (active_root / "sos-haruhi").exists()
    assert not (active_root / "sos-apify").exists()


def test_apply_rejects_loaded_plan_with_escaped_target_before_writes(tmp_path: Path):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"
    _write_config(codex_config_path, source / "SKILL.md")
    original_config_text = codex_config_path.read_text(encoding="utf-8")
    plan = _single_skill_plan(runtime_paths, active_root, codex_config_path)
    plan_path = tmp_path / "plan.toml"
    serialize_write_plan(plan, plan_path)
    tampered = read_toml(plan_path)
    for operation in tampered["operations"]:
        if operation["kind"] == OperationKind.COPY_SKILL.value:
            operation["target"] = str(tmp_path / "outside-vault" / "apify")
    write_toml(plan_path, tampered)

    loaded_plan = load_write_plan(plan_path)

    with pytest.raises(ValueError, match="escapes expected root"):
        apply_write_plan(
            loaded_plan,
            runtime_paths,
            codex_config_path,
            active_root,
            apply=True,
        )

    assert not runtime_paths.backups.exists()
    assert not runtime_paths.vault.exists()
    assert not runtime_paths.packs.exists()
    assert not runtime_paths.state.exists()
    assert not (active_root / "sos-haruhi").exists()
    assert codex_config_path.read_text(encoding="utf-8") == original_config_text


def _runtime_paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths.from_root(tmp_path / ".sos")


def _single_skill_plan(
    runtime_paths: RuntimePaths,
    active_root: Path,
    codex_config_path: Path,
) -> WritePlan:
    return build_pack_apply_plan(
        runtime_paths,
        active_root,
        codex_config_path,
        (
            PackProposal(
                pack_id="apify",
                skill_names=("apify-actor-development",),
                reason="Apify skill family.",
            ),
        ),
    )


def _write_skill(root: Path, name: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} test skill.\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill


def _write_config(config_path: Path, *skill_md_paths: Path) -> None:
    entries = "\n".join(
        f'[[skills.config]]\npath = "{skill_md_path}"\nenabled = true\n'
        for skill_md_path in skill_md_paths
    )
    config_path.write_text(entries, encoding="utf-8")
