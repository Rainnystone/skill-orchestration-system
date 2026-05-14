import os
import json
from pathlib import Path

import pytest

from sos.backups import create_backup
from sos.fingerprint import fingerprint_dir
from sos.manifest import save_pack_manifest, save_registry
from sos.models import PackManifest, Registry, SkillEntry
from sos.paths import RuntimePaths
from sos.pointer import render_companion_skill
from sos.cli import _runtime_manifest_fingerprint, main
from sos.recommendation_store import learned_reference_path, selection_events_path
from sos.toml_io import read_toml, write_toml


def test_cli_version_outputs_package_name(capsys):
    exit_code = main(["--version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "sos 0.1.0"


def test_scan_reads_root_without_writing(capsys, tmp_path: Path):
    root = tmp_path / "skills"
    _write_skill(root, "apify-actor-development")
    runtime_root = tmp_path / ".sos"

    exit_code = main(["scan", "--root", str(root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "apify-actor-development" in captured.out
    assert str(root / "apify-actor-development" / "SKILL.md") in captured.out
    assert not runtime_root.exists()


def test_scan_respects_codex_config_disabled_paths_without_writing(
    capsys,
    tmp_path: Path,
):
    root = tmp_path / "skills"
    _write_skill(root, "apify-actor-development")
    disabled_skill = _write_skill(root, "obsidian-cli")
    codex_config = _write_codex_config(
        tmp_path,
        disabled_paths=(disabled_skill / "SKILL.md",),
    )
    original_config = codex_config.read_text(encoding="utf-8")

    exit_code = main(["scan", "--root", str(root), "--codex-config", str(codex_config)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "apify-actor-development" in captured.out
    assert "obsidian-cli" not in captured.out
    assert codex_config.read_text(encoding="utf-8") == original_config


def test_propose_reports_builtin_packs_without_writing(capsys, tmp_path: Path):
    root = _write_builtin_pack_skills(tmp_path)
    runtime_root = tmp_path / ".sos"

    exit_code = main(["propose", "--root", str(root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "apify" in captured.out
    assert "obsidian" in captured.out
    assert "game-design" in captured.out
    assert "description: Use this for Apify" in captured.out
    assert "web scraping" in captured.out
    assert not runtime_root.exists()


def test_plan_writes_only_explicit_plan_file(capsys, tmp_path: Path):
    root = _write_builtin_pack_skills(tmp_path)
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = tmp_path / "plan.toml"
    original_config = codex_config.read_text(encoding="utf-8")

    exit_code = main(
        [
            "plan",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_root),
            "--codex-config",
            str(codex_config),
            "--out",
            str(plan_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert plan_path.is_file()
    assert "write plan" in captured.out
    assert str(plan_path) in captured.out
    assert "pack descriptions:" in captured.out
    assert "apify: Use this for Apify" in captured.out
    assert "web scraping" in captured.out
    assert not runtime_root.exists()
    assert codex_config.read_text(encoding="utf-8") == original_config
    assert (root / "apify-actor-development" / "SKILL.md").is_file()


def test_apply_without_apply_summarizes_plan_and_does_not_write(capsys, tmp_path: Path):
    root = _write_builtin_pack_skills(tmp_path)
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)
    original_config = codex_config.read_text(encoding="utf-8")

    exit_code = main(["apply", "--plan", str(plan_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "requires_apply: true" in captured.out
    assert "pack descriptions:" in captured.out
    assert "apify: Use this for Apify" in captured.out
    assert "web scraping" in captured.out
    assert str(runtime_root / "vault" / "apify" / "apify-actor-development") in captured.out
    assert not runtime_root.exists()
    assert codex_config.read_text(encoding="utf-8") == original_config
    assert not (root / "sos-apify").exists()


def test_apply_with_apply_executes_plan(capsys, tmp_path: Path):
    root = _write_builtin_pack_skills(tmp_path)
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)

    exit_code = main(["apply", "--plan", str(plan_path), "--apply"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "applied" in captured.out
    assert (runtime_root / "vault" / "apify" / "apify-actor-development" / "SKILL.md").is_file()
    assert (runtime_root / "packs" / "apify.toml").is_file()
    assert (runtime_root / "state" / "registry.toml").is_file()
    assert (root / "sos-haruhi" / "SKILL.md").is_file()
    assert (root / "sos-apify" / "SKILL.md").is_file()
    assert _disabled_config_paths(codex_config) == {
        str(root / "apify-actor-development" / "SKILL.md"),
        str(root / "obsidian-cli" / "SKILL.md"),
        str(root / "game-studio" / "SKILL.md"),
    }


def test_delete_source_requires_delete_source_apply_and_confirmation_phrase(
    tmp_path: Path,
):
    root = tmp_path / "skills"
    source = _write_skill(root, "apify-actor-development")
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)

    cases = (
        (
            ["apply", "--plan", str(plan_path), "--apply", "--confirm-delete-source", "apify"],
            "--confirm-delete-source requires --delete-source",
        ),
        (
            [
                "apply",
                "--plan",
                str(plan_path),
                "--delete-source",
                "--confirm-delete-source",
                "apify",
            ],
            "--delete-source requires --apply",
        ),
        (
            ["apply", "--plan", str(plan_path), "--apply", "--delete-source"],
            "--delete-source requires --confirm-delete-source",
        ),
    )

    for argv, message in cases:
        with pytest.raises(ValueError, match=message):
            main(argv)
        assert (source / "SKILL.md").is_file()


def test_delete_source_prints_exact_deleted_paths(capsys, tmp_path: Path):
    root = tmp_path / "skills"
    source = _write_skill(root, "apify-actor-development")
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)

    exit_code = main(
        [
            "apply",
            "--plan",
            str(plan_path),
            "--apply",
            "--delete-source",
            "--confirm-delete-source",
            "apify",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"- {source}" in captured.out
    assert not source.exists()


def test_delete_source_refused_plugin_cache_path_is_not_printed_as_pending(
    capsys,
    tmp_path: Path,
):
    root = tmp_path / ".codex" / "plugins" / "cache"
    source = _write_skill(root, "apify-actor-development")
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)
    capsys.readouterr()

    with pytest.raises(ValueError, match="plugin cache"):
        main(
            [
                "apply",
                "--plan",
                str(plan_path),
                "--apply",
                "--delete-source",
                "--confirm-delete-source",
                "apify",
            ]
        )

    captured = capsys.readouterr()
    assert "source paths to delete" not in captured.out
    assert str(source) not in captured.out
    assert (source / "SKILL.md").is_file()


def test_delete_source_refused_claude_path_is_not_printed_as_pending(
    capsys,
    tmp_path: Path,
):
    root = tmp_path / ".claude" / "skills"
    source = _write_skill(root, "apify-actor-development")
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)
    capsys.readouterr()

    with pytest.raises(ValueError, match="Claude-specific"):
        main(
            [
                "apply",
                "--plan",
                str(plan_path),
                "--apply",
                "--delete-source",
                "--confirm-delete-source",
                "apify",
            ]
        )

    captured = capsys.readouterr()
    assert "source paths to delete" not in captured.out
    assert str(source) not in captured.out
    assert (source / "SKILL.md").is_file()


def test_pack_activate_clean_auto_syncs_vault_without_config_or_source_writes(
    capsys,
    tmp_path: Path,
):
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    source, vault = _write_sync_manifest(runtime_root, "apify")
    source_skill = source / "SKILL.md"
    source_skill.write_text("# Updated source\n", encoding="utf-8")
    original_config = codex_config.read_text(encoding="utf-8")

    exit_code = main(
        [
            "pack",
            "activate",
            "apify",
            "--runtime-root",
            str(runtime_root),
            "--sync=clean-auto",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "synced" in captured.out
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Updated source\n"
    assert source_skill.read_text(encoding="utf-8") == "# Updated source\n"
    assert codex_config.read_text(encoding="utf-8") == original_config


def test_pack_sync_without_apply_reports_plan_and_does_not_write(capsys, tmp_path: Path):
    runtime_root = tmp_path / ".sos"
    source, vault = _write_sync_manifest(runtime_root, "apify")
    (source / "SKILL.md").write_text("# Updated source\n", encoding="utf-8")
    original_vault = (vault / "SKILL.md").read_text(encoding="utf-8")
    original_manifest = (runtime_root / "packs" / "apify.toml").read_text(encoding="utf-8")

    exit_code = main(["pack", "sync", "apify", "--runtime-root", str(runtime_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "sync plan" in captured.out
    assert str(vault) in captured.out
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == original_vault
    assert (runtime_root / "packs" / "apify.toml").read_text(encoding="utf-8") == original_manifest


def test_pack_sync_with_apply_updates_vault_and_manifest(capsys, tmp_path: Path):
    runtime_root = tmp_path / ".sos"
    source, vault = _write_sync_manifest(runtime_root, "apify")
    (source / "SKILL.md").write_text("# Updated source\n", encoding="utf-8")

    exit_code = main(["pack", "sync", "apify", "--runtime-root", str(runtime_root), "--apply"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "synced" in captured.out
    assert (vault / "SKILL.md").read_text(encoding="utf-8") == "# Updated source\n"


def test_recommend_context_reports_recommendations_without_writing(
    capsys,
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Docs workspace\n", encoding="utf-8")
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )

    exit_code = main(
        [
            "recommend",
            "context",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "workspace_kinds: docs" in captured.out
    assert "runtime_packs: 1" in captured.out
    assert "- docs: documents" in captured.out
    assert not learned_reference_path(runtime_paths).exists()


def test_recommend_commands_redact_local_paths_from_stdout(capsys, tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Docs workspace\n", encoding="utf-8")
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "workspace-activation-plan.toml"

    assert (
        main(
            [
                "recommend",
                "context",
                "--workspace-root",
                str(workspace_root),
                "--runtime-root",
                str(runtime_paths.root),
            ]
        )
        == 0
    )
    context_output = capsys.readouterr().out

    assert (
        main(
            [
                "recommend",
                "activation-plan",
                "--workspace-root",
                str(workspace_root),
                "--runtime-root",
                str(runtime_paths.root),
                "--packs",
                "docs",
                "--out",
                str(plan_path),
            ]
        )
        == 0
    )
    plan_output = capsys.readouterr().out

    assert (
        main(
            [
                "recommend",
                "activate",
                "--plan",
                str(plan_path),
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
            ]
        )
        == 0
    )
    dry_run_output = capsys.readouterr().out

    assert (
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs workflow",
                "--scenario-tags",
                "docs,workflow",
                "--packs",
                "docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )
        == 0
    )
    record_output = capsys.readouterr().out

    assert main(["recommend", "learn", "--runtime-root", str(runtime_paths.root)]) == 0
    learn_output = capsys.readouterr().out

    combined_output = "\n".join(
        (context_output, plan_output, dry_run_output, record_output, learn_output)
    )
    _assert_output_omits_path_variants(
        combined_output,
        tmp_path,
        workspace_root,
        runtime_paths.root,
        plan_path,
    )
    assert "WORKSPACE_ROOT" in combined_output
    assert "RUNTIME_ROOT" in combined_output
    assert "WORKSPACE_PLAN" in combined_output


def test_recommend_activation_plan_and_activate_apply(capsys, tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Docs workspace\n", encoding="utf-8")
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "workspace-activation-plan.toml"

    plan_exit = main(
        [
            "recommend",
            "activation-plan",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    )
    plan_output = capsys.readouterr().out

    activate_exit = main(
        [
            "recommend",
            "activate",
            "--plan",
            str(plan_path),
            "--runtime-root",
            str(runtime_paths.root),
            "--workspace-root",
            str(workspace_root),
            "--apply",
        ]
    )
    activate_output = capsys.readouterr().out

    workspace_skills = workspace_root / ".agents" / "skills"
    assert plan_exit == 0
    assert "workspace activation plan" in plan_output
    assert activate_exit == 0
    assert "apply status: applied" in activate_output
    assert (workspace_skills / "sos-nagato" / "SKILL.md").is_file()
    assert (workspace_skills / "sos-asahina" / "SKILL.md").is_file()
    assert (workspace_skills / "sos-docs" / "SKILL.md").is_file()


def test_recommend_activate_without_apply_is_dry_run(capsys, tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Docs workspace\n", encoding="utf-8")
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "workspace-activation-plan.toml"
    plan_exit = main(
        [
            "recommend",
            "activation-plan",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    )
    assert plan_exit == 0
    capsys.readouterr()

    activate_exit = main(
        [
            "recommend",
            "activate",
            "--plan",
            str(plan_path),
            "--runtime-root",
            str(runtime_paths.root),
            "--workspace-root",
            str(workspace_root),
        ]
    )

    captured = capsys.readouterr()
    assert activate_exit == 0
    assert "dry-run workspace activation; no external files written" in captured.out
    assert not (workspace_root / ".agents").exists()
    assert not learned_reference_path(runtime_paths).exists()


def test_recommend_activate_rejects_tampered_workspace_root(
    capsys,
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    tampered_workspace_root = tmp_path / "other-workspace"
    tampered_workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "workspace-activation-plan.toml"
    plan_exit = main(
        [
            "recommend",
            "activation-plan",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    )
    assert plan_exit == 0
    capsys.readouterr()
    _retarget_workspace_activation_plan(
        plan_path,
        tampered_workspace_root / ".agents" / "skills",
    )

    with pytest.raises(
        ValueError,
        match="workspace activation plan workspace root does not match",
    ):
        main(
            [
                "recommend",
                "activate",
                "--plan",
                str(plan_path),
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--apply",
            ]
        )

    assert not (tampered_workspace_root / ".agents").exists()


def test_recommend_record_selection_and_learn(capsys, tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )

    first_record_output = ""
    for index in range(10):
        exit_code = main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs workflow",
                "--scenario-tags",
                "docs,workflow",
                "--packs",
                "docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        if index == 0:
            first_record_output = captured.out

    learn_exit = main(
        [
            "recommend",
            "learn",
            "--runtime-root",
            str(runtime_paths.root),
            "--apply",
        ]
    )

    captured = capsys.readouterr()
    assert learn_exit == 0
    learned_path = learned_reference_path(runtime_paths)
    events_path = selection_events_path(runtime_paths)
    raw_events = events_path.read_text(encoding="utf-8")
    event_payload = json.loads(raw_events.splitlines()[0])
    assert learned_path.exists()
    assert "Evidence: 10 accepted selections" in learned_path.read_text(encoding="utf-8")
    assert "learned reference: applied RUNTIME_ROOT/state/recommendations/asahina-reference.md" in captured.out
    assert str(learned_path) not in captured.out
    assert str(workspace_root) not in raw_events
    assert event_payload["workspace_id"].startswith("sha256:")
    assert str(workspace_root) not in first_record_output


def test_recommend_learn_skips_history_that_does_not_match_runtime_manifests(
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    stale_events = []
    for index in range(10):
        stale_events.append(
            {
                "schema_version": 1,
                "created_at": f"2026-05-12T10:00:0{index}+00:00",
                "workspace_id": "sha256:stale",
                "scenario_label": "docs",
                "scenario_tags": ["docs"],
                "selected_pack_ids": ["web"],
                "selected_skill_names": ["documents"],
                "manifest_fingerprint": "sha256:stale",
                "selection_source": "user_accepted",
                "outcome": "activated",
            }
        )
        stale_events.append(
            {
                "schema_version": 1,
                "created_at": f"2026-05-12T10:01:0{index}+00:00",
                "workspace_id": "sha256:old-docs",
                "scenario_label": "docs",
                "scenario_tags": ["docs"],
                "selected_pack_ids": ["docs"],
                "selected_skill_names": ["removed-skill"],
                "manifest_fingerprint": "sha256:old-docs",
                "selection_source": "user_accepted",
                "outcome": "activated",
            }
        )
    events_path = selection_events_path(runtime_paths)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in stale_events),
        encoding="utf-8",
    )

    learn_exit = main(
        [
            "recommend",
            "learn",
            "--runtime-root",
            str(runtime_paths.root),
            "--apply",
        ]
    )

    assert learn_exit == 0
    learned_text = learned_reference_path(runtime_paths).read_text(encoding="utf-8")
    assert "Prefer recommending: web" not in learned_text
    assert "Prefer recommending: docs" not in learned_text
    assert "Status: empty" in learned_text


def test_recommend_learn_skips_history_with_stale_manifest_fingerprint(
    tmp_path: Path,
):
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    stale_events = [
        {
            "schema_version": 1,
            "created_at": f"2026-05-12T10:00:0{index}+00:00",
            "workspace_id": "sha256:stale-manifest",
            "scenario_label": "docs",
            "scenario_tags": ["docs"],
            "selected_pack_ids": ["docs"],
            "selected_skill_names": ["documents"],
            "manifest_fingerprint": "sha256:old-runtime-manifest",
            "selection_source": "user_accepted",
            "outcome": "activated",
        }
        for index in range(10)
    ]
    events_path = selection_events_path(runtime_paths)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in stale_events),
        encoding="utf-8",
    )

    learn_exit = main(
        [
            "recommend",
            "learn",
            "--runtime-root",
            str(runtime_paths.root),
            "--apply",
        ]
    )

    assert learn_exit == 0
    learned_text = learned_reference_path(runtime_paths).read_text(encoding="utf-8")
    assert "Prefer recommending: docs" not in learned_text
    assert "Status: empty" in learned_text


def test_recommend_record_selection_canonicalizes_duplicate_and_ordered_values(
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )

    exit_code = main(
        [
            "recommend",
            "record-selection",
            "--runtime-root",
            str(runtime_paths.root),
            "--workspace-root",
            str(workspace_root),
            "--scenario-label",
            "docs",
            "--scenario-tags",
            "docs",
            "--packs",
            "docs,docs",
            "--skills",
            "documents,documents",
            "--manifest-fingerprint",
            _runtime_manifest_fingerprint(runtime_paths),
        ]
    )

    raw_events = selection_events_path(runtime_paths).read_text(encoding="utf-8")
    event_payload = json.loads(raw_events)
    assert exit_code == 0
    assert event_payload["selected_pack_ids"] == ["docs"]
    assert event_payload["selected_skill_names"] == ["documents"]


def test_recommend_activation_plan_claude_host_and_activate_apply(
    capsys,
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "README.md").write_text("# Docs workspace\n", encoding="utf-8")
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "claude-workspace-plan.toml"

    plan_exit = main(
        [
            "recommend",
            "activation-plan",
            "--host",
            "claude",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    )
    capsys.readouterr()
    activate_exit = main(
        [
            "recommend",
            "activate",
            "--host",
            "claude",
            "--plan",
            str(plan_path),
            "--runtime-root",
            str(runtime_paths.root),
            "--workspace-root",
            str(workspace_root),
            "--apply",
        ]
    )
    activate_output = capsys.readouterr().out

    claude_skills = workspace_root / ".claude" / "skills"
    assert plan_exit == 0
    assert activate_exit == 0
    assert "apply status: applied" in activate_output
    assert (claude_skills / "sos-nagato" / "SKILL.md").is_file()
    assert (claude_skills / "sos-asahina" / "SKILL.md").is_file()
    assert (claude_skills / "sos-docs" / "SKILL.md").is_file()
    assert not (workspace_root / ".agents").exists()


def test_recommend_activate_uses_plan_host_when_host_argument_is_omitted(
    capsys,
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "claude-workspace-plan.toml"
    assert main(
        [
            "recommend",
            "activation-plan",
            "--host",
            "claude",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    ) == 0
    capsys.readouterr()

    activate_exit = main(
        [
            "recommend",
            "activate",
            "--plan",
            str(plan_path),
            "--runtime-root",
            str(runtime_paths.root),
            "--workspace-root",
            str(workspace_root),
            "--apply",
        ]
    )

    assert activate_exit == 0
    assert (workspace_root / ".claude" / "skills" / "sos-nagato" / "SKILL.md").is_file()


def test_recommend_activate_rejects_explicit_host_mismatch_before_writing(
    capsys,
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "claude-workspace-plan.toml"
    assert main(
        [
            "recommend",
            "activation-plan",
            "--host",
            "claude",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    ) == 0
    capsys.readouterr()

    with pytest.raises(ValueError, match="plan host"):
        main(
            [
                "recommend",
                "activate",
                "--host",
                "codex",
                "--plan",
                str(plan_path),
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--apply",
            ]
        )

    assert not (workspace_root / ".claude").exists()
    assert not (workspace_root / ".agents").exists()


def test_recommend_activate_apply_returns_nonzero_on_failed_apply(
    capsys,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    plan_path = tmp_path / "workspace-activation-plan.toml"
    plan_exit = main(
        [
            "recommend",
            "activation-plan",
            "--workspace-root",
            str(workspace_root),
            "--runtime-root",
            str(runtime_paths.root),
            "--packs",
            "docs",
            "--out",
            str(plan_path),
        ]
    )
    assert plan_exit == 0
    capsys.readouterr()

    def fail_asahina(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("sos.workspace_activation.render_asahina_skill", fail_asahina)

    exit_code = main(
        [
            "recommend",
            "activate",
            "--plan",
            str(plan_path),
            "--runtime-root",
            str(runtime_paths.root),
            "--workspace-root",
            str(workspace_root),
            "--apply",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "apply status: failed" in captured.out
    assert "message: boom" in captured.out


def test_recommend_record_selection_rejects_empty_packs_and_skills(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )

    with pytest.raises(ValueError, match="--packs must include at least one value"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs",
                "--scenario-tags",
                "docs",
                "--packs",
                ",",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    with pytest.raises(ValueError, match="--skills must include at least one value"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs workflow",
                "--scenario-tags",
                "docs",
                "--packs",
                "docs",
                "--skills",
                ",",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )


def test_recommend_record_selection_rejects_unsafe_persisted_values(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )

    with pytest.raises(ValueError, match="unsafe scenario_label"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                r"C:\Users\private\prompt",
                "--scenario-tags",
                "docs",
                "--packs",
                "docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    with pytest.raises(ValueError, match="unsafe scenario_tag"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs workflow",
                "--scenario-tags",
                "docs,/private/path",
                "--packs",
                "docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    with pytest.raises(ValueError, match="unsafe scenario_label"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "please summarize secret board deck",
                "--scenario-tags",
                "docs,deck",
                "--packs",
                "docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    assert not selection_events_path(runtime_paths).exists()


def test_recommend_record_selection_rejects_unknown_runtime_pack_or_skill(
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )

    with pytest.raises(ValueError, match="unknown selected pack"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs",
                "--scenario-tags",
                "docs",
                "--packs",
                "not-a-real-pack",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    with pytest.raises(ValueError, match="selected skill not in selected packs"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs",
                "--scenario-tags",
                "docs",
                "--packs",
                "docs",
                "--skills",
                "not-a-real-skill",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    assert not selection_events_path(runtime_paths).exists()


def test_recommend_record_selection_rejects_pack_without_selected_skill(
    tmp_path: Path,
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    runtime_paths, _ = _write_two_runtime_packs(tmp_path / ".sos")

    with pytest.raises(ValueError, match="selected pack has no selected skills"):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(workspace_root),
                "--scenario-label",
                "docs browser",
                "--scenario-tags",
                "docs,browser",
                "--packs",
                "browser,docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )

    assert not selection_events_path(runtime_paths).exists()


def test_recommend_learn_preview_does_not_write_reference(capsys, tmp_path: Path):
    runtime_paths, _ = _write_runtime_pack(
        tmp_path / ".sos",
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    selection_events_path(runtime_paths).parent.mkdir(parents=True, exist_ok=True)
    for index in range(10):
        main(
            [
                "recommend",
                "record-selection",
                "--runtime-root",
                str(runtime_paths.root),
                "--workspace-root",
                str(tmp_path / "workspace"),
                "--scenario-label",
                "docs",
                "--scenario-tags",
                "docs",
                "--packs",
                "docs",
                "--skills",
                "documents",
                "--manifest-fingerprint",
                _runtime_manifest_fingerprint(runtime_paths),
            ]
        )
    capsys.readouterr()

    exit_code = main(["recommend", "learn", "--runtime-root", str(runtime_paths.root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "learned reference preview:" in captured.out
    assert not learned_reference_path(runtime_paths).exists()


def test_pack_list_reports_runtime_packs_without_writing(capsys, tmp_path: Path):
    runtime_paths, _ = _write_runtime_pack(tmp_path / ".sos")
    registry_path = runtime_paths.state / "registry.toml"
    original_registry = registry_path.read_text(encoding="utf-8")

    exit_code = main(["pack", "list", "--runtime-root", str(runtime_paths.root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "packs: 1" in captured.out
    assert "- apify: Apify" in captured.out
    assert "pointer: sos-apify" in captured.out
    assert "skills: 1" in captured.out
    assert "sync_policy: clean-auto" in captured.out
    assert registry_path.read_text(encoding="utf-8") == original_registry


def test_pack_show_reports_manifest_vault_and_skill_descriptions(capsys, tmp_path: Path):
    runtime_paths, manifest = _write_runtime_pack(tmp_path / ".sos")

    exit_code = main(["pack", "show", "apify", "--runtime-root", str(runtime_paths.root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"manifest: {runtime_paths.packs / 'apify.toml'}" in captured.out
    assert f"vault_root: {runtime_paths.vault / 'apify'}" in captured.out
    assert "pointer: sos-apify" in captured.out
    assert "apify-actor-development" in captured.out
    assert "Develop and debug Apify Actors." in captured.out
    assert f"source: {manifest.skills[0].source_path}" in captured.out
    assert f"vault: {manifest.skills[0].vault_path}" in captured.out


def test_pack_show_skill_filters_exact_match_and_rejects_unknown(capsys, tmp_path: Path):
    runtime_paths, manifest = _write_runtime_pack(tmp_path / ".sos")

    exit_code = main(
        [
            "pack",
            "show",
            "apify",
            "--runtime-root",
            str(runtime_paths.root),
            "--skill",
            manifest.skills[0].name,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skills: 1" in captured.out
    assert manifest.skills[0].name in captured.out

    with pytest.raises(ValueError, match="unknown skill.*missing-skill"):
        main(
            [
                "pack",
                "show",
                "apify",
                "--runtime-root",
                str(runtime_paths.root),
                "--skill",
                "missing-skill",
            ]
        )


def test_status_reports_runtime_registry_and_backups(capsys, tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(
            packs=(
                PackManifest(
                    id="apify",
                    display_name="Apify",
                    pointer_skill="sos-apify",
                ),
            ),
            active_pointers=("sos-haruhi", "sos-apify"),
            backup_generations=("backup-001",),
        ),
    )
    _write_backup_metadata(runtime_paths, "backup-001")

    exit_code = main(["status", "--runtime-root", str(runtime_paths.root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "runtime_root" in captured.out
    assert "apify" in captured.out
    assert "sos-apify" in captured.out
    assert "backups: 1" in captured.out


def test_changes_reports_new_unmanaged_skill_without_writing(capsys, tmp_path: Path):
    root = tmp_path / "skills"
    runtime_paths, _manifest = _write_runtime_pack(tmp_path / ".sos")
    new_skill = _write_skill(root, "new-docs-skill")
    codex_config = _write_codex_config(tmp_path)
    original_config = codex_config.read_text(encoding="utf-8")

    exit_code = main(
        [
            "changes",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_paths.root),
            "--codex-config",
            str(codex_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "new unmanaged skills: 1" in captured.out
    assert f"- {new_skill}" in captured.out
    assert codex_config.read_text(encoding="utf-8") == original_config


def test_changes_reports_stale_pointer_without_writing(capsys, tmp_path: Path):
    root = tmp_path / "skills"
    runtime_paths, manifest = _write_runtime_pack(tmp_path / ".sos")
    stale_pointer = root / manifest.pointer_skill / "SKILL.md"
    stale_pointer.parent.mkdir(parents=True, exist_ok=True)
    stale_pointer.write_text("# stale pointer\n", encoding="utf-8")
    render_companion_skill(
        root / "sos-haruhi" / "SKILL.md",
        runtime_paths.state / "registry.toml",
    )
    codex_config = _write_codex_config(tmp_path)
    original_stale = stale_pointer.read_text(encoding="utf-8")

    exit_code = main(
        [
            "changes",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_paths.root),
            "--codex-config",
            str(codex_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "pointer stale: 1" in captured.out
    assert f"- {stale_pointer}" in captured.out
    assert stale_pointer.read_text(encoding="utf-8") == original_stale


def test_changes_uses_current_pack_manifest_for_drift(capsys, tmp_path: Path):
    root = tmp_path / "skills"
    runtime_paths, manifest = _write_runtime_pack(tmp_path / ".sos")
    skill = manifest.skills[0]
    current_manifest = PackManifest(
        id=manifest.id,
        display_name=manifest.display_name,
        description=manifest.description,
        pointer_skill=manifest.pointer_skill,
        aliases=manifest.aliases,
        sync_policy=manifest.sync_policy,
        vault_root=manifest.vault_root,
        skills=(
            SkillEntry(
                name=skill.name,
                description=skill.description,
                source_path=skill.source_path,
                vault_path=skill.vault_path,
                origin=skill.origin,
                last_source_fingerprint=fingerprint_dir(skill.source_path),
                last_vault_fingerprint=fingerprint_dir(skill.vault_path),
                last_synced_at="2026-04-24T00:00:00+00:00",
            ),
        ),
    )
    stale_registry_manifest = PackManifest(
        id=manifest.id,
        display_name=manifest.display_name,
        description=manifest.description,
        pointer_skill=manifest.pointer_skill,
        aliases=manifest.aliases,
        sync_policy=manifest.sync_policy,
        vault_root=manifest.vault_root,
        skills=(
            SkillEntry(
                name=skill.name,
                description=skill.description,
                source_path=skill.source_path,
                vault_path=skill.vault_path,
                origin=skill.origin,
                last_source_fingerprint="sha256:stale-source",
                last_vault_fingerprint="sha256:stale-vault",
                last_synced_at="2026-04-23T00:00:00+00:00",
            ),
        ),
    )
    save_pack_manifest(runtime_paths.packs / "apify.toml", current_manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(
            packs=(stale_registry_manifest,),
            active_pointers=("sos-haruhi", "sos-apify"),
        ),
    )
    codex_config = _write_codex_config(
        tmp_path,
        disabled_paths=(skill.source_path / "SKILL.md",),
    )

    exit_code = main(
        [
            "changes",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_paths.root),
            "--codex-config",
            str(codex_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "source changed: 0" in captured.out
    assert "vault changed: 0" in captured.out


def test_changes_reports_unbaselined_source_vault_mismatch(
    capsys,
    tmp_path: Path,
):
    root = tmp_path / "skills"
    runtime_paths, manifest = _write_runtime_pack(tmp_path / ".sos")
    skill = manifest.skills[0]
    (skill.source_path / "SKILL.md").write_text("# Edited source\n", encoding="utf-8")
    codex_config = _write_codex_config(
        tmp_path,
        disabled_paths=(skill.source_path / "SKILL.md",),
    )

    exit_code = main(
        [
            "changes",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_paths.root),
            "--codex-config",
            str(codex_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "source changed: 1" in captured.out
    assert f"- {skill.source_path}" in captured.out


def test_changes_reports_source_and_vault_drift(capsys, tmp_path: Path):
    runtime_paths, manifest = _write_runtime_pack(tmp_path / ".sos")
    root = tmp_path / "skills"
    managed_source = _write_skill(root, "apify-actor-development")
    managed_vault = manifest.skills[0].vault_path
    managed_vault.joinpath("SKILL.md").write_text("# Changed vault\n", encoding="utf-8")
    manifest = PackManifest(
        id=manifest.id,
        display_name=manifest.display_name,
        description=manifest.description,
        pointer_skill=manifest.pointer_skill,
        aliases=manifest.aliases,
        sync_policy=manifest.sync_policy,
        vault_root=manifest.vault_root,
        skills=(
            SkillEntry(
                name="apify-actor-development",
                description="Develop and debug Apify Actors.",
                source_path=managed_source,
                vault_path=managed_vault,
                origin="codex",
                last_source_fingerprint="sha256:old-source",
                last_vault_fingerprint="sha256:old-vault",
            ),
        ),
    )
    save_pack_manifest(runtime_paths.packs / "apify.toml", manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(packs=(manifest,), active_pointers=("sos-haruhi", "sos-apify")),
    )
    codex_config = _write_codex_config(tmp_path)

    exit_code = main(
        [
            "changes",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_paths.root),
            "--codex-config",
            str(codex_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "source changed: 1" in captured.out
    assert "vault changed: 1" in captured.out
    assert "managed source unexpectedly enabled: 1" in captured.out


def test_pack_sync_after_apply_reports_ready_without_baseline_conflict(
    capsys,
    tmp_path: Path,
):
    root = tmp_path / "skills"
    _write_skill(root, "apify-actor-development")
    runtime_root = tmp_path / ".sos"
    codex_config = _write_codex_config(tmp_path)
    plan_path = _write_cli_plan(tmp_path, root, runtime_root, codex_config)
    apply_exit = main(["apply", "--plan", str(plan_path), "--apply"])

    sync_exit = main(["pack", "sync", "apify", "--runtime-root", str(runtime_root)])

    captured = capsys.readouterr()
    assert apply_exit == 0
    assert sync_exit == 0
    assert "status: ready" in captured.out
    assert "conflict" not in captured.out


def test_changes_does_not_report_disabled_unmanaged_skill_as_active(
    capsys,
    tmp_path: Path,
):
    root = tmp_path / "skills"
    disabled_skill = _write_skill(root, "disabled-docs-skill")
    runtime_paths, _manifest = _write_runtime_pack(tmp_path / ".sos")
    codex_config = _write_codex_config(
        tmp_path,
        disabled_paths=(disabled_skill / "SKILL.md",),
    )

    exit_code = main(
        [
            "changes",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_paths.root),
            "--codex-config",
            str(codex_config),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "new unmanaged skills: 0" in captured.out


def test_backup_list_restore_and_clean_commands(capsys, tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    codex_config, vault_root = _write_config_and_vault(tmp_path)
    first = _create_cli_restore_backup(runtime_paths, codex_config, vault_root, "first")
    second = _create_cli_restore_backup(runtime_paths, codex_config, vault_root, "second")

    list_exit = main(["backup", "list", "--runtime-root", str(runtime_paths.root)])

    list_output = capsys.readouterr().out
    assert list_exit == 0
    assert first.backup_id in list_output
    assert second.backup_id in list_output

    codex_config.write_text('model = "changed"\n', encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")
    restore_exit = main(
        [
            "restore",
            first.backup_id,
            "--runtime-root",
            str(runtime_paths.root),
            "--apply",
        ]
    )

    restore_output = capsys.readouterr().out
    assert restore_exit == 0
    assert "restored" in restore_output
    assert codex_config.read_text(encoding="utf-8") == 'model = "gpt-5.5"\n'
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# first\n"

    clean_exit = main(
        [
            "backup",
            "clean",
            "--runtime-root",
            str(runtime_paths.root),
            "--keep",
            "1",
            "--apply",
        ]
    )

    clean_output = capsys.readouterr().out
    assert clean_exit == 0
    assert "kept backups: 1" in clean_output
    assert sorted(path.name for path in runtime_paths.backups.iterdir()) == [second.backup_id]


def test_restore_without_apply_reports_dry_run_and_does_not_write(
    capsys,
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    codex_config, vault_root = _write_config_and_vault(tmp_path)
    backup = _create_cli_restore_backup(runtime_paths, codex_config, vault_root, "backup")
    codex_config.write_text('model = "changed"\n', encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")

    exit_code = main(
        [
            "restore",
            backup.backup_id,
            "--runtime-root",
            str(runtime_paths.root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry-run" in captured.out
    assert str(codex_config) in captured.out
    assert str(vault_root) in captured.out
    assert codex_config.read_text(encoding="utf-8") == 'model = "changed"\n'
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Changed\n"


def test_restore_refuses_metadata_without_explicit_targets_before_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    codex_config, vault_root = _write_config_and_vault(tmp_path)
    backup = create_backup(runtime_paths, codex_config, vault_root, "missing targets")
    codex_config.write_text('model = "changed"\n', encoding="utf-8")
    (vault_root / "SKILL.md").write_text("# Changed\n", encoding="utf-8")
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    for apply_args in ([], ["--apply"]):
        with pytest.raises(ValueError, match="vault_root"):
            main(
                [
                    "restore",
                    backup.backup_id,
                    "--runtime-root",
                    str(runtime_paths.root),
                    *apply_args,
                ]
            )

    assert codex_config.read_text(encoding="utf-8") == 'model = "changed"\n'
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Changed\n"
    assert not fake_home.exists()


def test_restore_rejects_unsafe_backup_id_without_reading_outside_metadata(
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    codex_config, vault_root = _write_config_and_vault(tmp_path)
    runtime_paths.backups.mkdir(parents=True)
    outside_dir = runtime_paths.root / "outside"
    outside_config = tmp_path / "outside-config.toml"
    outside_vault = tmp_path / "outside-vault"
    write_toml(
        outside_dir / "metadata.toml",
        {
            "backup_id": "outside",
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "outside",
            "codex_config_path": str(outside_config),
            "vault_root": str(outside_vault),
        },
    )

    with pytest.raises(ValueError, match="backup_id"):
        main(["restore", "../outside", "--runtime-root", str(runtime_paths.root)])

    assert codex_config.read_text(encoding="utf-8") == 'model = "gpt-5.5"\n'
    assert (vault_root / "SKILL.md").read_text(encoding="utf-8") == "# Original\n"
    assert not outside_config.exists()
    assert not outside_vault.exists()


def test_backup_clean_keep_20_with_apply_prunes_only_oldest_backups(
    capsys,
    tmp_path: Path,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    backup_ids = tuple(
        f"backup-20260424T1200{index:02d}000000Z" for index in range(22)
    )
    for backup_id in backup_ids:
        _write_backup_metadata(runtime_paths, backup_id)

    exit_code = main(
        [
            "backup",
            "clean",
            "--runtime-root",
            str(runtime_paths.root),
            "--keep",
            "20",
            "--apply",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "backup clean applied" in captured.out
    assert "keep: 20" in captured.out
    assert "kept backups: 20" in captured.out
    assert sorted(path.name for path in runtime_paths.backups.iterdir()) == sorted(
        backup_ids[2:]
    )


def test_backup_clean_without_apply_does_not_delete(capsys, tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    _write_backup_metadata(runtime_paths, "backup-20260424T120000000000Z")
    _write_backup_metadata(runtime_paths, "backup-20260424T120001000000Z")

    exit_code = main(
        [
            "backup",
            "clean",
            "--runtime-root",
            str(runtime_paths.root),
            "--keep",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry-run" in captured.out
    assert sorted(path.name for path in runtime_paths.backups.iterdir()) == [
        "backup-20260424T120000000000Z",
        "backup-20260424T120001000000Z",
    ]


def _write_skill(root: Path, name: str, body: str | None = None) -> Path:
    skill = root / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        body
        or f"---\nname: {name}\ndescription: {name} test skill.\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill


def _write_builtin_pack_skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    _write_skill(root, "apify-actor-development")
    _write_skill(root, "obsidian-cli")
    _write_skill(root, "game-studio")
    return root


def _write_codex_config(
    tmp_path: Path,
    disabled_paths: tuple[Path, ...] = (),
) -> Path:
    config_path = tmp_path / "config.toml"
    entries = [
        {"path": str(disabled_path), "enabled": False}
        for disabled_path in disabled_paths
    ]
    write_toml(config_path, {"model": "gpt-5.5", "skills": {"config": entries}})
    return config_path


def _write_cli_plan(
    tmp_path: Path,
    root: Path,
    runtime_root: Path,
    codex_config: Path,
) -> Path:
    plan_path = tmp_path / "plan.toml"
    exit_code = main(
        [
            "plan",
            "--root",
            str(root),
            "--runtime-root",
            str(runtime_root),
            "--codex-config",
            str(codex_config),
            "--out",
            str(plan_path),
        ]
    )
    assert exit_code == 0
    return plan_path


def _retarget_workspace_activation_plan(plan_path: Path, workspace_skill_root: Path) -> None:
    data = read_toml(plan_path)
    for operation in data["operations"]:
        if operation["kind"] not in {"write_workspace_skill", "write_pointer"}:
            continue
        skill_name = Path(operation["target"]).parent.name
        operation["target"] = str(workspace_skill_root / skill_name / "SKILL.md")
        metadata = operation.setdefault("metadata", {})
        metadata["workspace_skill_root"] = str(workspace_skill_root)
    write_toml(plan_path, data)


def _assert_output_omits_path_variants(output: str, *paths: Path) -> None:
    for path in paths:
        variants = {
            str(path),
            path.as_posix(),
            str(path.resolve(strict=False)),
            path.resolve(strict=False).as_posix(),
        }
        for variant in variants:
            assert variant not in output


def _disabled_config_paths(codex_config: Path) -> set[str]:
    entries = read_toml(codex_config)["skills"]["config"]
    return {str(entry["path"]) for entry in entries if entry.get("enabled") is False}


def _write_sync_manifest(runtime_root: Path, pack_id: str) -> tuple[Path, Path]:
    runtime_paths = RuntimePaths.from_root(runtime_root)
    source = _write_skill(runtime_root / "sources", "apify-actor-development", "# Original\n")
    vault = _write_skill(runtime_paths.vault / pack_id, "apify-actor-development", "# Original\n")
    manifest = PackManifest(
        id=pack_id,
        display_name=pack_id.title(),
        pointer_skill=f"sos-{pack_id}",
        sync_policy="clean-auto",
        vault_root=runtime_paths.vault / pack_id,
        skills=(
            SkillEntry(
                name="apify-actor-development",
                source_path=source,
                vault_path=vault,
                origin="codex",
                last_source_fingerprint=fingerprint_dir(source),
                last_vault_fingerprint=fingerprint_dir(vault),
                last_synced_at="2026-04-24T00:00:00+00:00",
            ),
        ),
    )
    save_pack_manifest(runtime_paths.packs / f"{pack_id}.toml", manifest)
    return source, vault


def _write_runtime_pack(
    runtime_root: Path,
    pack_id: str = "apify",
    skill_name: str = "apify-actor-development",
    skill_description: str = "Develop and debug Apify Actors.",
) -> tuple[RuntimePaths, PackManifest]:
    runtime_paths = RuntimePaths.from_root(runtime_root)
    source = _write_skill(runtime_root / "sources", skill_name, "# Original\n")
    vault = _write_skill(runtime_paths.vault / pack_id, skill_name, "# Original\n")
    manifest = PackManifest(
        id=pack_id,
        display_name=pack_id.title(),
        description="Shared source/tool family signal: Apify.",
        pointer_skill=f"sos-{pack_id}",
        aliases=(pack_id,),
        sync_policy="clean-auto",
        vault_root=runtime_paths.vault / pack_id,
        skills=(
            SkillEntry(
                name=skill_name,
                description=skill_description,
                source_path=source,
                vault_path=vault,
                origin="codex",
            ),
        ),
    )
    save_pack_manifest(runtime_paths.packs / f"{pack_id}.toml", manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(
            packs=(manifest,),
            active_pointers=("sos-haruhi", f"sos-{pack_id}"),
        ),
    )
    return runtime_paths, manifest


def _write_two_runtime_packs(runtime_root: Path) -> tuple[RuntimePaths, tuple[PackManifest, ...]]:
    runtime_paths, docs_manifest = _write_runtime_pack(
        runtime_root,
        pack_id="docs",
        skill_name="documents",
        skill_description="Create and edit docx documents.",
    )
    browser_source = _write_skill(
        runtime_root / "sources",
        "open-browser",
        "# Browser skill\n",
    )
    browser_vault = _write_skill(
        runtime_paths.vault / "browser",
        "open-browser",
        "# Browser skill\n",
    )
    browser_manifest = PackManifest(
        id="browser",
        display_name="Browser",
        description="Open pages, inspect web apps, and test browser flows.",
        pointer_skill="sos-browser",
        aliases=("browser",),
        sync_policy="clean-auto",
        vault_root=runtime_paths.vault / "browser",
        skills=(
            SkillEntry(
                name="open-browser",
                description="Navigate and inspect browser pages.",
                source_path=browser_source,
                vault_path=browser_vault,
                origin="codex",
            ),
        ),
    )
    save_pack_manifest(runtime_paths.packs / "browser.toml", browser_manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(
            packs=(docs_manifest, browser_manifest),
            active_pointers=("sos-haruhi", "sos-docs", "sos-browser"),
        ),
    )
    return runtime_paths, (docs_manifest, browser_manifest)


def _write_config_and_vault(tmp_path: Path) -> tuple[Path, Path]:
    codex_config = tmp_path / "config.toml"
    codex_config.write_text('model = "gpt-5.5"\n', encoding="utf-8")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "SKILL.md").write_text("# Original\n", encoding="utf-8")
    return codex_config, vault_root


def _create_cli_restore_backup(
    runtime_paths: RuntimePaths,
    codex_config: Path,
    vault_root: Path,
    label: str,
):
    codex_config.write_text('model = "gpt-5.5"\n', encoding="utf-8")
    (vault_root / "SKILL.md").write_text(f"# {label}\n", encoding="utf-8")
    record = create_backup(runtime_paths, codex_config, vault_root, label)
    metadata = dict(record.metadata)
    metadata["codex_config_path"] = str(codex_config)
    metadata["vault_root"] = str(vault_root)
    write_toml(runtime_paths.backups / record.backup_id / "metadata.toml", metadata)
    return record


def _write_backup_metadata(runtime_paths: RuntimePaths, backup_id: str) -> None:
    write_toml(
        runtime_paths.backups / backup_id / "metadata.toml",
        {
            "backup_id": backup_id,
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "seeded",
        },
    )


def test_cli_plan_defaults_to_codex_and_requires_codex_config(tmp_path):
    from sos.cli import main
    from sos.planner import load_write_plan

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo").mkdir()
    (skill_root / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_root = tmp_path / "runtime"
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    plan_out = tmp_path / "plan.toml"

    exit_code = main([
        "plan",
        "--root", str(skill_root),
        "--runtime-root", str(runtime_root),
        "--codex-config", str(codex_config_path),
        "--out", str(plan_out),
    ])
    assert exit_code == 0

    plan = load_write_plan(plan_out)
    assert plan.host == "codex"


def test_cli_plan_codex_without_codex_config_raises(tmp_path):
    from sos.cli import main
    import pytest

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo").mkdir()
    (skill_root / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_root = tmp_path / "runtime"
    plan_out = tmp_path / "plan.toml"

    with pytest.raises(ValueError, match="codex-config"):
        main([
            "plan",
            "--root", str(skill_root),
            "--runtime-root", str(runtime_root),
            "--out", str(plan_out),
        ])


def test_cli_plan_claude_without_codex_config(tmp_path):
    from sos.cli import main
    from sos.planner import load_write_plan

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo").mkdir()
    (skill_root / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_root = tmp_path / "runtime"
    plan_out = tmp_path / "plan.toml"

    exit_code = main([
        "plan",
        "--host", "claude",
        "--root", str(skill_root),
        "--runtime-root", str(runtime_root),
        "--out", str(plan_out),
    ])
    assert exit_code == 0
    plan = load_write_plan(plan_out)
    assert plan.host == "claude"


def test_cli_claude_relative_root_persists_absolute_restore_metadata(
    capsys,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    _write_skill(Path("skills"), "apify-actor-development")

    plan_exit = main(
        [
            "plan",
            "--host",
            "claude",
            "--root",
            "skills",
            "--runtime-root",
            "runtime",
            "--out",
            "plan.toml",
        ]
    )
    assert plan_exit == 0
    capsys.readouterr()

    apply_exit = main(["apply", "--plan", "plan.toml", "--apply"])
    assert apply_exit == 0
    apply_output = capsys.readouterr().out
    backup_id = next(
        line.removeprefix("backup_id: ")
        for line in apply_output.splitlines()
        if line.startswith("backup_id: ")
    )

    metadata = read_toml(tmp_path / "runtime" / "backups" / backup_id / "metadata.toml")
    active_skill_root = tmp_path / "skills"
    assert metadata["active_skill_root"] == active_skill_root.as_posix()
    assert Path(metadata["active_skill_root"]).is_absolute()
    entry = metadata["archive_restore_entries"][0]
    assert entry["source_path"] == (
        active_skill_root / "apify-actor-development"
    ).as_posix()
    assert entry["archive_path"] == (
        active_skill_root
        / ".sos-archive"
        / "apify"
        / "apify-actor-development"
    ).as_posix()

    restore_exit = main(
        ["restore", backup_id, "--runtime-root", "runtime", "--apply"]
    )

    assert restore_exit == 0
    assert (active_skill_root / "apify-actor-development" / "SKILL.md").is_file()


def test_cli_plan_claude_with_codex_config_rejected(tmp_path):
    from sos.cli import main
    import pytest

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo").mkdir()
    (skill_root / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_root = tmp_path / "runtime"
    plan_out = tmp_path / "plan.toml"
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="codex-config"):
        main([
            "plan",
            "--host", "claude",
            "--root", str(skill_root),
            "--runtime-root", str(runtime_root),
            "--codex-config", str(codex_config_path),
            "--out", str(plan_out),
        ])


def test_cli_apply_host_must_match_plan(tmp_path):
    from sos.cli import main
    from sos.planner import build_pack_apply_plan, serialize_write_plan
    from sos.paths import RuntimePaths
    from sos.propose import PackProposal

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "demo").mkdir()
    (skill_root / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
    )
    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")
    plan = build_pack_apply_plan(
        runtime_paths, skill_root, codex_config_path,
        (PackProposal(pack_id="demo", skill_names=("demo",), reason="test"),),
        host="claude",
    )
    plan_path = tmp_path / "plan.toml"
    serialize_write_plan(plan, plan_path)

    # Apply without --host falls back to plan.host (claude), so should NOT fail.
    # Apply with --host codex should fail because plan.host == claude.
    import pytest
    with pytest.raises(ValueError, match="plan host"):
        main(["apply", "--plan", str(plan_path), "--host", "codex"])


@pytest.mark.skipif(os.name != "nt", reason="backslash is path separator only on Windows")
def test_restore_rejects_backslash_traversal_on_windows(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    codex_config, vault_root = _write_config_and_vault(tmp_path)
    runtime_paths.backups.mkdir(parents=True)
    outside_dir = runtime_paths.root / "outside"
    outside_config = tmp_path / "outside-config.toml"
    outside_vault = tmp_path / "outside-vault"
    write_toml(
        outside_dir / "metadata.toml",
        {
            "backup_id": "outside",
            "created_at": "2026-04-24T12:00:00+00:00",
            "reason": "outside",
            "codex_config_path": str(outside_config),
            "vault_root": str(outside_vault),
        },
    )

    with pytest.raises(ValueError, match="backup_id"):
        main(["restore", "..\\outside", "--runtime-root", str(runtime_paths.root)])

    assert not outside_config.exists()
    assert not outside_vault.exists()


def test_cli_changes_claude_without_codex_config(tmp_path):
    from sos.cli import main

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    # changes is read-only; just confirm it runs without --codex-config under host=claude.
    exit_code = main([
        "changes",
        "--host", "claude",
        "--root", str(skill_root),
        "--runtime-root", str(runtime_root),
    ])
    assert exit_code == 0


def test_cli_changes_claude_with_codex_config_rejected(tmp_path):
    from sos.cli import main
    import pytest

    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    codex_config_path = tmp_path / "config.toml"
    codex_config_path.write_text("model = \"x\"\n[skills]\nconfig = []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="codex-config"):
        main([
            "changes",
            "--host", "claude",
            "--root", str(skill_root),
            "--runtime-root", str(runtime_root),
            "--codex-config", str(codex_config_path),
        ])
