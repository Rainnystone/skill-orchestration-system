from __future__ import annotations

import os
import shutil
from collections import Counter
from pathlib import Path

import pytest

from sos.cli import main
from sos.manifest import load_pack_manifest
from sos.models import OperationKind
from sos.planner import load_write_plan
from sos.propose import propose_builtin_packs
from sos.scanner import scan_skill_roots
from sos.toml_io import read_toml


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SKILL_ROOT = REPO_ROOT / "tests" / "fixtures" / "skills"
FIXTURE_CODEX_CONFIG = REPO_ROOT / "tests" / "fixtures" / "codex" / "config.toml"
REFERENCE_DOCS = (
    REPO_ROOT / "references" / "pointer-skill-authoring.md",
    REPO_ROOT / "references" / "manifest-schema.md",
    REPO_ROOT / "references" / "activation-flow.md",
    REPO_ROOT / "references" / "sync-policy.md",
    REPO_ROOT / "references" / "codex-config-safety.md",
    REPO_ROOT / "references" / "backup-restore.md",
)


def test_reference_docs_exist_and_use_current_cli_terms() -> None:
    for doc in REFERENCE_DOCS:
        assert doc.is_file(), f"missing reference doc: {doc}"

    combined = "\n".join(doc.read_text(encoding="utf-8") for doc in REFERENCE_DOCS)
    for command in (
        "sos scan",
        "sos propose",
        "sos plan",
        "sos apply",
        "sos status",
        "sos pack activate",
        "sos pack sync",
        "sos backup list",
        "sos backup clean",
        "sos restore",
    ):
        assert command in combined

    for field in (
        "id",
        "display_name",
        "aliases",
        "description",
        "pointer_skill",
        "sync_policy",
        "paths.vault_root",
        "skills.name",
        "skills.source_path",
        "skills.vault_path",
        "skills.origin",
        "skills.enabled_before_apply",
        "triggers",
    ):
        assert field in combined


def test_fixture_roots_propose_builtin_apify_obsidian_and_game_packs() -> None:
    skills = scan_skill_roots((FIXTURE_SKILL_ROOT,))

    proposals = propose_builtin_packs(skills)

    by_pack = {proposal.pack_id: proposal.skill_names for proposal in proposals}
    assert by_pack["apify"] == ("apify-actor-development",)
    assert by_pack["obsidian"] == ("obsidian-cli",)
    assert by_pack["game-design"] == ("game-studio",)


def test_fixture_apply_path_disables_originals_and_leaves_pointers_scannable(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    active_root = tmp_path / "skills"
    shutil.copytree(FIXTURE_SKILL_ROOT, active_root)
    runtime_root = tmp_path / ".sos"
    codex_config = tmp_path / "config.toml"
    shutil.copy2(FIXTURE_CODEX_CONFIG, codex_config)
    plan_path = tmp_path / "plan.toml"

    plan_exit = main(
        [
            "plan",
            "--root",
            str(active_root),
            "--runtime-root",
            str(runtime_root),
            "--codex-config",
            str(codex_config),
            "--out",
            str(plan_path),
        ]
    )

    assert plan_exit == 0
    capsys.readouterr()
    plan = load_write_plan(plan_path)
    operation_counts = Counter(operation.kind for operation in plan.operations)
    assert operation_counts == {
        OperationKind.BACKUP_CODEX_CONFIG: 1,
        OperationKind.BACKUP_VAULT: 1,
        OperationKind.COPY_SKILL: 3,
        OperationKind.WRITE_MANIFEST: 3,
        OperationKind.WRITE_REGISTRY: 1,
        OperationKind.WRITE_POINTER: 4,
        OperationKind.DISABLE_CODEX_SKILL: 3,
        OperationKind.DELETE_SOURCE: 3,
    }
    assert plan.pack_ids == ("apify", "obsidian", "game-design")
    assert not runtime_root.exists()

    dry_run_exit = main(["apply", "--plan", str(plan_path)])
    assert dry_run_exit == 0
    capsys.readouterr()
    assert not runtime_root.exists()

    apply_exit = main(["apply", "--plan", str(plan_path), "--apply"])

    assert apply_exit == 0
    capsys.readouterr()
    disabled_paths = _disabled_config_paths(codex_config)
    assert disabled_paths == {
        str(active_root / "apify-actor-development" / "SKILL.md"),
        str(active_root / "obsidian-cli" / "SKILL.md"),
        str(active_root / "game-studio" / "SKILL.md"),
    }

    for pack_id in plan.pack_ids:
        manifest = load_pack_manifest(runtime_root / "packs" / f"{pack_id}.toml")
        pointer = active_root / manifest.pointer_skill / "SKILL.md"
        pointer_text = pointer.read_text(encoding="utf-8")
        assert str(runtime_root / "packs" / f"{pack_id}.toml") in pointer_text
        assert str(runtime_root / "vault" / pack_id) in pointer_text
        for skill in manifest.skills:
            assert skill.vault_path == runtime_root / "vault" / pack_id / skill.name
            assert (skill.vault_path / "SKILL.md").is_file()

    scan_exit = main(
        ["scan", "--root", str(active_root), "--codex-config", str(codex_config)]
    )
    captured = capsys.readouterr()
    assert scan_exit == 0
    assert "sos-apify" in captured.out
    assert "sos-obsidian" in captured.out
    assert "sos-game-design" in captured.out
    assert "sos-haruhi" in captured.out
    assert "apify-actor-development" not in captured.out
    assert "obsidian-cli" not in captured.out
    assert "game-studio" not in captured.out


def test_opt_in_real_skill_roots_stay_dry_run_only() -> None:
    raw_roots = os.environ.get("SOS_REAL_SKILL_ROOTS")
    if not raw_roots:
        pytest.skip("SOS_REAL_SKILL_ROOTS is not set")

    roots = tuple(
        Path(raw_root).expanduser()
        for raw_root in raw_roots.split(os.pathsep)
        if raw_root.strip()
    )
    existing_roots = tuple(root for root in roots if root.is_dir())
    if not existing_roots:
        pytest.skip("SOS_REAL_SKILL_ROOTS does not contain existing directories")

    skills = scan_skill_roots(existing_roots)
    proposals = propose_builtin_packs(skills)
    pack_ids = {proposal.pack_id for proposal in proposals}
    expected = {"apify", "obsidian", "game-design"}
    missing = expected - pack_ids
    if missing:
        pytest.skip(
            "SOS_REAL_SKILL_ROOTS lacks matching skills for: "
            + ", ".join(sorted(missing))
        )

    assert expected <= pack_ids


def _disabled_config_paths(codex_config: Path) -> set[str]:
    entries = read_toml(codex_config)["skills"]["config"]
    return {str(entry["path"]) for entry in entries if entry.get("enabled") is False}
