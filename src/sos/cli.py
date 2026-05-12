from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sos import __version__
from sos.apply import apply_write_plan
from sos.backups import list_backups, prune_backups, restore_backup
from sos.changes import detect_changes
from sos.codex_config import load_codex_config
from sos.manifest import load_registry
from sos.models import OperationKind, SkillEntry, WriteOperation, WritePlan
from sos.pack_inspect import filter_pack_skill, list_pack_manifests, load_runtime_pack
from sos.paths import RuntimePaths
from sos.planner import (
    build_pack_apply_plan,
    load_write_plan,
    serialize_write_plan,
    summarize_write_plan,
)
from sos.propose import propose_builtin_packs
from sos.recommendation_engine import build_recommendation_context, recommend_packs
from sos.recommendation_store import (
    SelectionEvent,
    append_selection_event,
    build_learned_reference,
    canonicalize_scenario_tags,
    learned_reference_path,
    load_selection_events,
    scenario_label_from_tags,
    workspace_id_for_path,
    write_learned_reference,
)
from sos.scanner import ScannedSkill, scan_skill_roots
from sos.sync import activate_pack, apply_pack_sync, plan_pack_sync
from sos.toml_io import read_toml, write_toml
from sos.workspace_activation import (
    apply_workspace_activation_plan,
    build_workspace_activation_plan,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"sos {__version__}")
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    return int(args.handler(args))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sos")
    parser.add_argument(
        "--version",
        action="store_true",
        help="print version and exit",
    )
    subcommands = parser.add_subparsers(dest="command")

    scan = subcommands.add_parser("scan", help="scan skill roots")
    scan.add_argument("--root", required=True)
    scan.add_argument("--codex-config")
    scan.set_defaults(handler=_handle_scan)

    propose = subcommands.add_parser("propose", help="propose built-in packs")
    propose.add_argument("--root", required=True)
    propose.set_defaults(handler=_handle_propose)

    plan = subcommands.add_parser("plan", help="write an auditable apply plan")
    plan.add_argument("--root", required=True)
    plan.add_argument("--runtime-root", required=True)
    plan.add_argument("--codex-config", required=True)
    plan.add_argument("--out", required=True)
    plan.set_defaults(handler=_handle_plan)

    apply = subcommands.add_parser("apply", help="summarize or apply a write plan")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--apply", action="store_true")
    apply.add_argument("--delete-source", action="store_true")
    apply.add_argument("--confirm-delete-source")
    apply.set_defaults(handler=_handle_apply)

    pack = subcommands.add_parser("pack", help="pack activation and sync")
    pack_subcommands = pack.add_subparsers(dest="pack_command", required=True)

    activate = pack_subcommands.add_parser("activate", help="activate a pack")
    activate.add_argument("pack")
    activate.add_argument("--runtime-root", required=True)
    activate.add_argument("--sync", default="clean-auto")
    activate.set_defaults(handler=_handle_pack_activate)

    sync = pack_subcommands.add_parser("sync", help="plan or apply pack sync")
    sync.add_argument("pack")
    sync.add_argument("--runtime-root", required=True)
    sync.add_argument("--apply", action="store_true")
    sync.set_defaults(handler=_handle_pack_sync)

    pack_list = pack_subcommands.add_parser("list", help="list runtime packs")
    pack_list.add_argument("--runtime-root", required=True)
    pack_list.set_defaults(handler=_handle_pack_list)

    show = pack_subcommands.add_parser("show", help="show runtime pack details")
    show.add_argument("pack")
    show.add_argument("--runtime-root", required=True)
    show.add_argument("--skill")
    show.set_defaults(handler=_handle_pack_show)

    status = subcommands.add_parser("status", help="summarize runtime status")
    status.add_argument("--runtime-root", required=True)
    status.set_defaults(handler=_handle_status)

    changes = subcommands.add_parser("changes", help="report runtime drift without writing")
    changes.add_argument("--root", required=True)
    changes.add_argument("--runtime-root", required=True)
    changes.add_argument("--codex-config", required=True)
    changes.set_defaults(handler=_handle_changes)

    backup = subcommands.add_parser("backup", help="backup management")
    backup_subcommands = backup.add_subparsers(dest="backup_command", required=True)

    backup_list = backup_subcommands.add_parser("list", help="list backups")
    backup_list.add_argument("--runtime-root", required=True)
    backup_list.set_defaults(handler=_handle_backup_list)

    backup_clean = backup_subcommands.add_parser("clean", help="prune old backups")
    backup_clean.add_argument("--runtime-root", required=True)
    backup_clean.add_argument("--keep", type=int, required=True)
    backup_clean.add_argument("--apply", action="store_true")
    backup_clean.set_defaults(handler=_handle_backup_clean)

    restore = subcommands.add_parser("restore", help="restore a backup")
    restore.add_argument("backup_id")
    restore.add_argument("--runtime-root", required=True)
    restore.add_argument("--apply", action="store_true")
    restore.set_defaults(handler=_handle_restore)

    recommend = subcommands.add_parser("recommend", help="workspace recommendation workflow")
    recommend_subcommands = recommend.add_subparsers(
        dest="recommend_command",
        required=True,
    )

    recommend_context = recommend_subcommands.add_parser(
        "context",
        help="inspect workspace recommendation context",
    )
    recommend_context.add_argument("--workspace-root", required=True)
    recommend_context.add_argument("--runtime-root", required=True)
    recommend_context.add_argument("--intent", default="")
    recommend_context.set_defaults(handler=_handle_recommend_context)

    recommend_activation_plan = recommend_subcommands.add_parser(
        "activation-plan",
        help="write a workspace activation plan",
    )
    recommend_activation_plan.add_argument("--workspace-root", required=True)
    recommend_activation_plan.add_argument("--runtime-root", required=True)
    recommend_activation_plan.add_argument("--packs", required=True)
    recommend_activation_plan.add_argument("--out", required=True)
    recommend_activation_plan.set_defaults(handler=_handle_recommend_activation_plan)

    recommend_activate = recommend_subcommands.add_parser(
        "activate",
        help="summarize or apply a workspace activation plan",
    )
    recommend_activate.add_argument("--plan", required=True)
    recommend_activate.add_argument("--runtime-root", required=True)
    recommend_activate.add_argument("--workspace-root", required=True)
    recommend_activate.add_argument("--apply", action="store_true")
    recommend_activate.set_defaults(handler=_handle_recommend_activate)

    recommend_record_selection = recommend_subcommands.add_parser(
        "record-selection",
        help="record an accepted workspace recommendation selection",
    )
    recommend_record_selection.add_argument("--runtime-root", required=True)
    recommend_record_selection.add_argument("--workspace-root", required=True)
    recommend_record_selection.add_argument("--scenario-label", required=True)
    recommend_record_selection.add_argument("--scenario-tags", required=True)
    recommend_record_selection.add_argument("--packs", required=True)
    recommend_record_selection.add_argument("--skills", required=True)
    recommend_record_selection.add_argument("--manifest-fingerprint", required=True)
    recommend_record_selection.set_defaults(handler=_handle_recommend_record_selection)

    recommend_learn = recommend_subcommands.add_parser(
        "learn",
        help="build or apply the learned recommendation reference",
    )
    recommend_learn.add_argument("--runtime-root", required=True)
    recommend_learn.add_argument("--apply", action="store_true")
    recommend_learn.set_defaults(handler=_handle_recommend_learn)

    return parser


def _handle_scan(args: argparse.Namespace) -> int:
    skills = _scan_from_args(args.root, getattr(args, "codex_config", None))
    print(f"scan root: {Path(args.root)}")
    print(f"skills: {len(skills)}")
    for skill in skills:
        print(f"- {skill.name}: {skill.skill_md}")
        if skill.description:
            print(f"  description: {skill.description}")
    return 0


def _handle_propose(args: argparse.Namespace) -> int:
    skills = _scan_from_args(args.root, None)
    proposals = propose_builtin_packs(skills)
    print(f"proposal root: {Path(args.root)}")
    print(f"proposals: {len(proposals)}")
    for proposal in proposals:
        print(f"- {proposal.pack_id}: {', '.join(proposal.skill_names)}")
        print(f"  reason: {proposal.reason}")
        if proposal.description:
            print(f"  description: {proposal.description}")
    return 0


def _handle_plan(args: argparse.Namespace) -> int:
    root = Path(args.root)
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    codex_config_path = Path(args.codex_config)
    out = Path(args.out)
    skills = scan_skill_roots(
        (root,),
        disabled_paths=_disabled_paths_from_config(codex_config_path),
    )
    proposals = propose_builtin_packs(skills)
    plan = build_pack_apply_plan(runtime_paths, root, codex_config_path, proposals)
    serialize_write_plan(plan, out)
    print(f"write plan: {out}")
    print(summarize_write_plan(plan))
    return 0


def _handle_apply(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = load_write_plan(plan_path)
    context = _context_from_plan(plan)
    _validate_delete_source_args(args)
    result = apply_write_plan(
        plan,
        context["runtime_paths"],
        context["codex_config_path"],
        context["active_skill_root"],
        apply=bool(args.apply),
        delete_source=bool(args.delete_source),
        confirm_delete_source=args.confirm_delete_source,
    )
    if not args.apply:
        print("dry-run apply; no external files written")
        print(summarize_write_plan(plan))
        return 0

    if result.backup_id:
        _annotate_backup_metadata(
            context["runtime_paths"],
            result.backup_id,
            codex_config_path=context["codex_config_path"],
            active_skill_root=context["active_skill_root"],
        )
    print(f"apply status: {result.status}")
    if result.backup_id:
        print(f"backup_id: {result.backup_id}")
    if result.message:
        print(f"message: {result.message}")
    if result.deleted_source_paths:
        print("deleted source paths:")
        for path in result.deleted_source_paths:
            print(f"- {path}")
    return 0


def _handle_pack_activate(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    manifest_path = _manifest_path(runtime_paths, args.pack)
    result = activate_pack(manifest_path, sync_policy=args.sync)
    print(f"pack: {result.pack_id}")
    print(f"status: {result.status}")
    print(f"manifest: {result.manifest_path}")
    for message in result.messages:
        print(f"- {message}")
    _print_operations(result.operations)
    return 0


def _handle_pack_sync(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    manifest_path = _manifest_path(runtime_paths, args.pack)
    sync_plan = plan_pack_sync(manifest_path)
    result = apply_pack_sync(sync_plan, apply=bool(args.apply))
    print("sync plan" if not args.apply else "sync apply")
    print(f"pack: {result.pack_id}")
    print(f"status: {result.status}")
    print(f"manifest: {result.manifest_path}")
    for message in result.messages:
        print(f"- {message}")
    _print_operations(result.operations)
    return 0


def _handle_pack_list(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    manifests = list_pack_manifests(runtime_paths)
    print(f"pack root: {runtime_paths.packs}")
    print(f"packs: {len(manifests)}")
    for manifest in manifests:
        print(f"- {manifest.id}: {manifest.display_name}")
        print(f"  pointer: {manifest.pointer_skill}")
        print(f"  skills: {len(manifest.skills)}")
        print(f"  sync_policy: {manifest.sync_policy}")
        if manifest.description:
            print(f"  description: {manifest.description}")
    return 0


def _handle_pack_show(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    manifest = load_runtime_pack(runtime_paths, args.pack)
    if args.skill:
        manifest = filter_pack_skill(manifest, args.skill)
    print(f"pack: {manifest.id}")
    print(f"display_name: {manifest.display_name}")
    print(f"manifest: {runtime_paths.packs / f'{manifest.id}.toml'}")
    print(f"vault_root: {manifest.vault_root or ''}")
    print(f"pointer: {manifest.pointer_skill}")
    print(f"aliases: {', '.join(manifest.aliases)}")
    print(f"sync_policy: {manifest.sync_policy}")
    if manifest.description:
        print(f"description: {manifest.description}")
    print(f"skills: {len(manifest.skills)}")
    for skill in manifest.skills:
        print(f"- {skill.name}")
        if skill.description:
            print(f"  description: {skill.description}")
        print(f"  source: {skill.source_path}")
        print(f"  vault: {skill.vault_path}")
        print(f"  origin: {skill.origin}")
        if skill.last_source_fingerprint:
            print(f"  last_source_fingerprint: {skill.last_source_fingerprint}")
        if skill.last_vault_fingerprint:
            print(f"  last_vault_fingerprint: {skill.last_vault_fingerprint}")
    return 0


def _handle_status(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    registry_path = runtime_paths.state / "registry.toml"
    backups = list_backups(runtime_paths)
    print(f"runtime_root: {runtime_paths.root}")
    print(f"vault: {runtime_paths.vault}")
    print(f"packs_dir: {runtime_paths.packs}")
    print(f"state_dir: {runtime_paths.state}")
    if registry_path.is_file():
        registry = load_registry(registry_path)
        print(f"packs: {', '.join(pack.id for pack in registry.packs)}")
        print(f"active_pointers: {', '.join(registry.active_pointers)}")
    else:
        print("packs: none")
        print("active_pointers: none")
    print(f"backups: {len(backups)}")
    if backups:
        print(f"latest_backup: {backups[0].backup_id}")
    return 0


def _handle_changes(args: argparse.Namespace) -> int:
    root = Path(args.root)
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    report = detect_changes(root, runtime_paths, Path(args.codex_config))
    print(f"scan root: {root}")
    print(f"runtime_root: {runtime_paths.root}")
    _print_path_section("new unmanaged skills", report.new_unmanaged)
    _print_skill_section("source missing", report.source_missing, "source_path")
    _print_skill_section("source changed", report.source_changed, "source_path")
    _print_skill_section("vault changed", report.vault_changed, "vault_path")
    _print_path_section("pointer missing", report.pointer_missing)
    _print_path_section("pointer stale", report.pointer_stale)
    _print_skill_section(
        "managed source unexpectedly enabled",
        report.managed_source_enabled,
        "source_path",
    )
    print("next safe actions:")
    print("- review listed paths before any plan or apply step")
    print("- disable managed source skills in Codex config if they should stay vault-managed")
    print("- restore missing pointers or re-run the relevant pack workflow after review")
    return 0


def _handle_backup_list(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    backups = list_backups(runtime_paths)
    print(f"backup root: {runtime_paths.backups}")
    print(f"backups: {len(backups)}")
    for backup in backups:
        print(f"- {backup.backup_id}: {backup.created_at.isoformat()}")
        if backup.config_path is not None:
            print(f"  config_snapshot: {backup.config_path}")
        if backup.vault_path is not None:
            print(f"  vault_snapshot: {backup.vault_path}")
    return 0


def _handle_restore(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    codex_config_path, vault_root = _restore_targets(runtime_paths, args.backup_id)
    if not args.apply:
        print("dry-run restore; no external files written")
        print(f"backup_id: {args.backup_id}")
        print(f"codex_config_path: {codex_config_path}")
        print(f"vault_root: {vault_root}")
        return 0
    record = restore_backup(
        runtime_paths,
        args.backup_id,
        codex_config_path,
        vault_root,
        apply=True,
    )
    print(f"restored: {record.backup_id}")
    print(f"codex_config_path: {codex_config_path}")
    print(f"vault_root: {vault_root}")
    return 0


def _handle_backup_clean(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    kept = prune_backups(runtime_paths, keep=args.keep, apply=bool(args.apply))
    print("backup clean applied" if args.apply else "backup clean dry-run; no backups deleted")
    print(f"backup root: {runtime_paths.backups}")
    print(f"keep: {args.keep}")
    print(f"kept backups: {len(kept)}")
    for backup in kept:
        print(f"- {backup.backup_id}")
    return 0


def _handle_recommend_context(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    context = build_recommendation_context(
        runtime_paths,
        args.workspace_root,
        intent=args.intent,
    )
    recommendations = recommend_packs(context)
    learned_path = learned_reference_path(runtime_paths)
    workspace_kinds = ", ".join(context.workspace_signal.kinds) or "none"
    print("workspace_root: WORKSPACE_ROOT")
    print(f"workspace_id: {context.workspace_id}")
    print(f"workspace_kinds: {workspace_kinds}")
    print(f"runtime_packs: {len(context.pack_manifests)}")
    print(
        "learned_reference: "
        + ("present" if learned_path.is_file() else "missing")
    )
    print(f"learned_reference_path: {_redacted_runtime_path(learned_path, runtime_paths)}")
    print(f"selection_events: {len(context.selection_events)}")
    print(f"recommendations: {len(recommendations)}")
    for recommendation in recommendations:
        print(f"- {recommendation.pack_id}: {', '.join(recommendation.skill_names)}")
        print(f"  reason: {recommendation.reason}")
    return 0


def _handle_recommend_activation_plan(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    out = Path(args.out)
    plan = build_workspace_activation_plan(
        runtime_paths,
        args.workspace_root,
        _csv_tuple(args.packs),
    )
    serialize_write_plan(plan, out)
    print("workspace activation plan: WORKSPACE_PLAN")
    print(
        _redacted_recommendation_plan_summary(
            plan,
            runtime_paths,
            args.workspace_root,
            plan_path=out,
        )
    )
    return 0


def _handle_recommend_activate(args: argparse.Namespace) -> int:
    plan = load_write_plan(Path(args.plan))
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    result = apply_workspace_activation_plan(
        plan,
        runtime_paths,
        workspace_root=args.workspace_root,
        apply=bool(args.apply),
    )
    if not args.apply:
        print("dry-run workspace activation; no external files written")
        print(
            _redacted_recommendation_plan_summary(
                plan,
                runtime_paths,
                args.workspace_root,
                plan_path=Path(args.plan),
            )
        )
        return 0
    print(f"apply status: {result.status}")
    if result.message:
        print(f"message: {result.message}")
    return 0 if result.status == "applied" else 1


def _handle_recommend_record_selection(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    selected_pack_ids = _csv_tuple(args.packs)
    if not selected_pack_ids:
        raise ValueError("--packs must include at least one value")
    selected_skill_names = _csv_tuple(args.skills)
    if not selected_skill_names:
        raise ValueError("--skills must include at least one value")
    scenario_tags = _csv_tuple(args.scenario_tags)
    _validate_scenario_label_argument(args.scenario_label, scenario_tags)
    scenario_tags = canonicalize_scenario_tags(scenario_tags)
    selected_pack_ids, selected_skill_names = _validate_recommendation_selection(
        runtime_paths,
        selected_pack_ids,
        selected_skill_names,
    )
    event = SelectionEvent(
        schema_version=1,
        created_at=_utc_now_isoformat(),
        workspace_id=workspace_id_for_path(args.workspace_root),
        scenario_label=scenario_label_from_tags(scenario_tags),
        scenario_tags=scenario_tags,
        selected_pack_ids=selected_pack_ids,
        selected_skill_names=selected_skill_names,
        manifest_fingerprint=args.manifest_fingerprint,
        selection_source="user_accepted",
        outcome="activated",
    )
    path = append_selection_event(runtime_paths, event)
    print(f"selection event: {_redacted_runtime_path(path, runtime_paths)}")
    print(
        "recorded selection: "
        f"{event.scenario_label}; packs={', '.join(event.selected_pack_ids)}; "
        f"skills={', '.join(event.selected_skill_names)}"
    )
    return 0


def _handle_recommend_learn(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    reference = build_learned_reference(load_selection_events(runtime_paths))
    path = write_learned_reference(runtime_paths, reference, apply=bool(args.apply))
    if not args.apply:
        print("learned reference preview:")
        print(reference.rstrip())
        print(f"path: {_redacted_runtime_path(path, runtime_paths)}")
        return 0
    print(f"learned reference: applied {_redacted_runtime_path(path, runtime_paths)}")
    return 0


def _redacted_recommendation_plan_summary(
    plan: WritePlan,
    runtime_paths: RuntimePaths,
    workspace_root: str | Path,
    *,
    plan_path: str | Path | None = None,
) -> str:
    replacements: list[tuple[Path, str]] = [
        (Path(workspace_root), "WORKSPACE_ROOT"),
        (runtime_paths.root, "RUNTIME_ROOT"),
    ]
    if plan_path is not None:
        replacements.append((Path(plan_path), "WORKSPACE_PLAN"))
    return _redact_local_paths(summarize_write_plan(plan), replacements)


def _validate_recommendation_selection(
    runtime_paths: RuntimePaths,
    selected_pack_ids: tuple[str, ...],
    selected_skill_names: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    runtime_manifests = list_pack_manifests(runtime_paths)
    manifests_by_id = {manifest.id: manifest for manifest in runtime_manifests}
    selected_pack_set = set(selected_pack_ids)
    for pack_id in selected_pack_ids:
        if pack_id not in manifests_by_id:
            raise ValueError(f"unknown selected pack: {pack_id}")
    canonical_pack_ids = tuple(
        manifest.id for manifest in runtime_manifests if manifest.id in selected_pack_set
    )

    selected_manifests = tuple(manifests_by_id[pack_id] for pack_id in canonical_pack_ids)
    skill_names = {
        skill.name
        for manifest in selected_manifests
        for skill in manifest.skills
    }
    for skill_name in selected_skill_names:
        if skill_name not in skill_names:
            raise ValueError(f"selected skill not in selected packs: {skill_name}")
    selected_skill_set = set(selected_skill_names)
    canonical_skill_names: list[str] = []
    for manifest in selected_manifests:
        if not any(skill.name in selected_skill_set for skill in manifest.skills):
            raise ValueError(f"selected pack has no selected skills: {manifest.id}")
        for skill in manifest.skills:
            if skill.name in selected_skill_set and skill.name not in canonical_skill_names:
                canonical_skill_names.append(skill.name)
    return canonical_pack_ids, tuple(canonical_skill_names)


def _validate_scenario_label_argument(
    scenario_label: str,
    scenario_tags: tuple[str, ...],
) -> None:
    accepted_labels = {
        " ".join(dict.fromkeys(scenario_tags)),
        scenario_label_from_tags(canonicalize_scenario_tags(scenario_tags)),
    }
    if scenario_label.strip() not in accepted_labels:
        raise ValueError(f"unsafe scenario_label: {scenario_label}")


def _redacted_runtime_path(path: str | Path, runtime_paths: RuntimePaths) -> str:
    return _redact_local_paths(str(path), ((runtime_paths.root, "RUNTIME_ROOT"),))


def _redact_local_paths(text: str, replacements: Iterable[tuple[Path, str]]) -> str:
    redacted = text
    path_replacements: list[tuple[str, str]] = []
    for path, replacement in replacements:
        for variant in _path_variants(path):
            path_replacements.append((variant, replacement))
    for variant, replacement in sorted(
        path_replacements,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        redacted = redacted.replace(variant, replacement)
    return redacted.replace("\\", "/")


def _path_variants(path: Path) -> tuple[str, ...]:
    candidates = (
        path,
        path.expanduser(),
        path.expanduser().resolve(strict=False),
    )
    variants: set[str] = set()
    for candidate in candidates:
        variants.add(str(candidate))
        variants.add(candidate.as_posix())
    return tuple(variant for variant in variants if variant)


def _scan_from_args(
    root: str | Path,
    codex_config_path: str | Path | None,
) -> tuple[ScannedSkill, ...]:
    return scan_skill_roots(
        (Path(root),),
        disabled_paths=_disabled_paths_from_config(codex_config_path),
    )


def _disabled_paths_from_config(codex_config_path: str | Path | None) -> tuple[Path, ...]:
    if codex_config_path is None:
        return ()
    path = Path(codex_config_path)
    if not path.exists():
        return ()
    config = load_codex_config(path)
    skills = config.get("skills", {})
    if not isinstance(skills, dict):
        return ()
    entries = skills.get("config", ())
    if not isinstance(entries, list):
        return ()
    return tuple(
        Path(str(entry["path"]))
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("enabled") is False
        and "path" in entry
    )


def _context_from_plan(plan: WritePlan) -> dict[str, Any]:
    backup_vault = _single_operation(plan, OperationKind.BACKUP_VAULT)
    backup_config = _single_operation(plan, OperationKind.BACKUP_CODEX_CONFIG)
    runtime_vault = _required_path(backup_vault.source)
    active_root = _active_root_from_plan(plan)
    return {
        "runtime_paths": RuntimePaths.from_root(runtime_vault.parent),
        "codex_config_path": _required_path(backup_config.source),
        "active_skill_root": active_root,
    }


def _active_root_from_plan(plan: WritePlan) -> Path:
    copy_operations = _operations_of_kind(plan, OperationKind.COPY_SKILL)
    if copy_operations:
        return _required_path(copy_operations[0].source).parent
    pointer_operations = _operations_of_kind(plan, OperationKind.WRITE_POINTER)
    if pointer_operations:
        return _required_path(pointer_operations[0].target).parent.parent
    raise ValueError("unable to infer active skill root from plan")


def _validate_delete_source_args(args: argparse.Namespace) -> None:
    if args.confirm_delete_source is not None and not args.delete_source:
        raise ValueError("--confirm-delete-source requires --delete-source")
    if args.delete_source and not args.apply:
        raise ValueError("--delete-source requires --apply")
    if args.delete_source and args.confirm_delete_source is None:
        raise ValueError("--delete-source requires --confirm-delete-source")


def _restore_targets(runtime_paths: RuntimePaths, backup_id: str) -> tuple[Path, Path]:
    _safe_component(backup_id, "backup_id")
    metadata_path = runtime_paths.backups / backup_id / "metadata.toml"
    metadata = read_toml(metadata_path)
    if "codex_config_path" not in metadata or "vault_root" not in metadata:
        raise ValueError(
            "backup restore metadata must include codex_config_path and vault_root"
        )
    return Path(str(metadata["codex_config_path"])), Path(str(metadata["vault_root"]))


def _annotate_backup_metadata(
    runtime_paths: RuntimePaths,
    backup_id: str,
    codex_config_path: Path,
    active_skill_root: Path,
) -> None:
    metadata_path = runtime_paths.backups / backup_id / "metadata.toml"
    if not metadata_path.exists():
        return
    metadata = read_toml(metadata_path)
    next_metadata = {
        **metadata,
        "codex_config_path": str(codex_config_path),
        "vault_root": str(runtime_paths.vault),
        "active_skill_root": str(active_skill_root),
    }
    write_toml(metadata_path, next_metadata)


def _manifest_path(runtime_paths: RuntimePaths, pack_id: str) -> Path:
    _safe_component(pack_id, "pack")
    return runtime_paths.packs / f"{pack_id}.toml"


def _print_path_section(label: str, paths: Sequence[Path]) -> None:
    print(f"{label}: {len(paths)}")
    for path in paths:
        print(f"- {path}")


def _print_skill_section(label: str, skills: Sequence[SkillEntry], attr: str) -> None:
    print(f"{label}: {len(skills)}")
    for skill in skills:
        print(f"- {getattr(skill, attr)}")


def _print_operations(operations: tuple[WriteOperation, ...]) -> None:
    if not operations:
        return
    print("operations:")
    for operation in operations:
        target = operation.target if operation.target is not None else operation.source
        print(f"- {operation.kind.value}: {target}")


def _operations_of_kind(
    plan: WritePlan,
    kind: OperationKind,
) -> tuple[WriteOperation, ...]:
    return tuple(operation for operation in plan.operations if operation.kind == kind)


def _single_operation(plan: WritePlan, kind: OperationKind) -> WriteOperation:
    operations = _operations_of_kind(plan, kind)
    if len(operations) != 1:
        raise ValueError(f"expected exactly one {kind.value} operation")
    return operations[0]


def _required_path(path: Path | None) -> Path:
    if path is None:
        raise ValueError("operation path is required")
    return path


def _safe_component(value: str, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
        or Path(value).name != value
    ):
        raise ValueError(f"unsafe {label}: {value}")
    return value


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat()
