from pathlib import Path

import pytest

from sos.models import OperationKind
from sos.paths import RuntimePaths
from sos.planner import (
    build_pack_apply_plan,
    load_write_plan,
    serialize_write_plan,
    summarize_write_plan,
)
from sos.propose import PackProposal


def _write_skill(root: Path, name: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} test skill.\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill


def _runtime_paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths.from_root(tmp_path / ".sos")


def _apify_proposal() -> PackProposal:
    return PackProposal(
        pack_id="apify",
        skill_names=("apify-actor-development",),
        reason="Apify skill family.",
    )


def test_plan_apply_contains_all_write_operations_without_writing(tmp_path: Path):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    codex_config_path = tmp_path / "config.toml"

    plan = build_pack_apply_plan(
        runtime_paths,
        active_root,
        codex_config_path,
        (_apify_proposal(),),
    )

    assert plan.requires_apply is True
    assert plan.delete_source_requested is False
    assert plan.second_confirmation is False
    assert plan.pack_ids == ("apify",)
    assert set(operation.kind for operation in plan.operations) >= {
        OperationKind.BACKUP_CODEX_CONFIG,
        OperationKind.BACKUP_VAULT,
        OperationKind.COPY_SKILL,
        OperationKind.WRITE_MANIFEST,
        OperationKind.WRITE_REGISTRY,
        OperationKind.WRITE_POINTER,
        OperationKind.DISABLE_CODEX_SKILL,
        OperationKind.DELETE_SOURCE,
    }

    assert not runtime_paths.vault.exists()
    assert not runtime_paths.packs.exists()
    assert not runtime_paths.backups.exists()
    assert not runtime_paths.state.exists()
    assert not (active_root / "sos-haruhi").exists()
    assert not (active_root / "sos-apify").exists()
    assert not codex_config_path.exists()
    assert source.is_dir()


def test_plan_serializes_config_backup_manifest_registry_pointer_and_disable_operations(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)
    plan_path = tmp_path / "plan.toml"

    plan = build_pack_apply_plan(
        runtime_paths,
        active_root,
        tmp_path / "config.toml",
        (_apify_proposal(),),
    )

    serialize_write_plan(plan, plan_path)
    loaded = load_write_plan(plan_path)

    assert loaded.plan_id == plan.plan_id
    assert loaded.pack_ids == ("apify",)
    assert loaded.requires_apply is True
    assert loaded.delete_source_requested is False
    assert loaded.second_confirmation is False
    assert tuple(operation.kind for operation in loaded.operations) == (
        OperationKind.BACKUP_CODEX_CONFIG,
        OperationKind.BACKUP_VAULT,
        OperationKind.COPY_SKILL,
        OperationKind.WRITE_MANIFEST,
        OperationKind.WRITE_REGISTRY,
        OperationKind.WRITE_POINTER,
        OperationKind.WRITE_POINTER,
        OperationKind.DISABLE_CODEX_SKILL,
        OperationKind.DELETE_SOURCE,
    )
    assert loaded.operations[0].target == runtime_paths.backups / plan.plan_id / "config.toml"
    assert dict(loaded.operations[0].metadata)["codex_config_path"] == str(
        tmp_path / "config.toml"
    )
    assert loaded.operations[2].source == source
    assert loaded.operations[2].target == runtime_paths.vault / "apify" / source.name
    assert dict(loaded.operations[3].metadata)["manifest"]["id"] == "apify"
    assert dict(loaded.operations[4].metadata)["registry"]["active_pointers"] == [
        "sos-haruhi",
        "sos-apify",
    ]
    assert dict(loaded.operations[5].metadata) == {
        "pointer_skill": "sos-haruhi",
        "role": "companion",
    }
    assert dict(loaded.operations[7].metadata)["skill_md_path"] == str(source / "SKILL.md")


def test_plan_lists_source_deletion_candidates_without_enabling_deletion(tmp_path: Path):
    active_root = tmp_path / "active"
    source = _write_skill(active_root, "apify-actor-development")

    plan = build_pack_apply_plan(
        _runtime_paths(tmp_path),
        active_root,
        tmp_path / "config.toml",
        (_apify_proposal(),),
    )

    summary = summarize_write_plan(plan)

    assert plan.delete_source_requested is False
    assert plan.second_confirmation is False
    assert str(source) in summary
    assert "delete_source_requested: false" in summary
    assert "candidate only" in summary
    delete_operations = [
        operation
        for operation in plan.operations
        if operation.kind == OperationKind.DELETE_SOURCE
    ]
    assert len(delete_operations) == 1
    assert dict(delete_operations[0].metadata)["candidate"] is True


def test_plan_rejects_unvalidated_source_paths(tmp_path: Path):
    active_root = tmp_path / "active"
    (active_root / "apify-actor-development").mkdir(parents=True)

    with pytest.raises(ValueError, match="Missing SKILL.md"):
        build_pack_apply_plan(
            _runtime_paths(tmp_path),
            active_root,
            tmp_path / "config.toml",
            (_apify_proposal(),),
        )


def test_plan_rejects_unsafe_pack_id_without_writing_targets(tmp_path: Path):
    active_root = tmp_path / "active"
    _write_skill(active_root, "apify-actor-development")
    runtime_paths = _runtime_paths(tmp_path)

    with pytest.raises(ValueError, match="unsafe pack_id"):
        build_pack_apply_plan(
            runtime_paths,
            active_root,
            tmp_path / "config.toml",
            (
                PackProposal(
                    pack_id="../escape",
                    skill_names=("apify-actor-development",),
                    reason="Unsafe pack.",
                ),
            ),
        )

    assert not runtime_paths.vault.exists()
    assert not runtime_paths.packs.exists()
    assert not runtime_paths.state.exists()
    assert not runtime_paths.backups.exists()
    assert not (active_root / "sos-..").exists()


def test_plan_rejects_unsafe_skill_name_even_when_outside_folder_is_valid(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    active_root.mkdir()
    outside = _write_skill(tmp_path, "outside-skill")
    runtime_paths = _runtime_paths(tmp_path)

    with pytest.raises(ValueError, match="unsafe skill_name"):
        build_pack_apply_plan(
            runtime_paths,
            active_root,
            tmp_path / "config.toml",
            (
                PackProposal(
                    pack_id="apify",
                    skill_names=("../outside-skill",),
                    reason="Unsafe skill.",
                ),
            ),
        )

    assert outside.is_dir()
    assert not runtime_paths.vault.exists()
    assert not runtime_paths.packs.exists()
    assert not runtime_paths.state.exists()
    assert not runtime_paths.backups.exists()


def test_plan_preserves_multi_pack_and_multi_skill_operation_order(tmp_path: Path):
    active_root = tmp_path / "active"
    _write_skill(active_root, "apify-actor-development")
    _write_skill(active_root, "apify-ecommerce")
    _write_skill(active_root, "obsidian-cli")
    runtime_paths = _runtime_paths(tmp_path)

    plan = build_pack_apply_plan(
        runtime_paths,
        active_root,
        tmp_path / "config.toml",
        (
            PackProposal(
                pack_id="apify",
                skill_names=("apify-actor-development", "apify-ecommerce"),
                reason="Apify skill family.",
            ),
            PackProposal(
                pack_id="obsidian",
                skill_names=("obsidian-cli",),
                reason="Obsidian skill family.",
            ),
        ),
    )

    assert plan.pack_ids == ("apify", "obsidian")
    assert [
        (operation.kind, operation.metadata.get("pack_id"), operation.metadata.get("skill_name"))
        for operation in plan.operations
        if operation.kind
        in {
            OperationKind.COPY_SKILL,
            OperationKind.WRITE_MANIFEST,
            OperationKind.DISABLE_CODEX_SKILL,
            OperationKind.DELETE_SOURCE,
        }
    ] == [
        (OperationKind.COPY_SKILL, "apify", "apify-actor-development"),
        (OperationKind.COPY_SKILL, "apify", "apify-ecommerce"),
        (OperationKind.COPY_SKILL, "obsidian", "obsidian-cli"),
        (OperationKind.WRITE_MANIFEST, "apify", None),
        (OperationKind.WRITE_MANIFEST, "obsidian", None),
        (OperationKind.DISABLE_CODEX_SKILL, "apify", "apify-actor-development"),
        (OperationKind.DISABLE_CODEX_SKILL, "apify", "apify-ecommerce"),
        (OperationKind.DISABLE_CODEX_SKILL, "obsidian", "obsidian-cli"),
        (OperationKind.DELETE_SOURCE, "apify", "apify-actor-development"),
        (OperationKind.DELETE_SOURCE, "apify", "apify-ecommerce"),
        (OperationKind.DELETE_SOURCE, "obsidian", "obsidian-cli"),
    ]
