from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from sos import __version__
from sos.apply import apply_write_plan
from sos.backups import (
    annotate_backup_metadata,
    list_backups,
    prune_backups,
    restore_backup,
    restore_targets,
)
from sos.changes import detect_changes
from sos.codex_config import disabled_paths_from_config, resolve_codex_config_arg
from sos.manifest import load_registry
from sos.models import SkillEntry, WriteOperation, WritePlan
from sos.pack_inspect import (
    filter_pack_skill,
    list_pack_manifests,
    load_runtime_pack,
    runtime_manifest_fingerprint,
)
from sos.path_safety import safe_component
from sos.paths import RuntimePaths
from sos.planner import (
    build_pack_apply_plan,
    context_from_plan,
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
    manifest_valid_selection_events,
    scenario_label_from_tags,
    validate_recommendation_selection,
    validate_scenario_label_argument,
    workspace_id_for_path,
    write_learned_reference,
)
from sos.redaction import (
    redacted_recommendation_plan_summary,
    redacted_runtime_path,
)
from sos.scanner import ScannedSkill, scan_skill_roots
from sos.sync import activate_pack, apply_pack_sync, plan_pack_sync
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
    plan.add_argument("--codex-config", default=None)
    plan.add_argument("--out", required=True)
    plan.add_argument("--host", choices=("codex", "claude"), default="codex")
    plan.set_defaults(handler=_handle_plan)

    apply = subcommands.add_parser("apply", help="summarize or apply a write plan")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--apply", action="store_true")
    apply.add_argument("--delete-source", action="store_true")
    apply.add_argument("--confirm-delete-source")
    apply.add_argument("--host", choices=("codex", "claude"), default=None)
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
    changes.add_argument("--codex-config", default=None)
    changes.add_argument("--host", choices=("codex", "claude"), default="codex")
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
    recommend_activation_plan.add_argument("--host", choices=("codex", "claude"), default="codex")
    recommend_activation_plan.set_defaults(handler=_handle_recommend_activation_plan)

    recommend_activate = recommend_subcommands.add_parser(
        "activate",
        help="summarize or apply a workspace activation plan",
    )
    recommend_activate.add_argument("--plan", required=True)
    recommend_activate.add_argument("--runtime-root", required=True)
    recommend_activate.add_argument("--workspace-root", required=True)
    recommend_activate.add_argument("--apply", action="store_true")
    recommend_activate.add_argument("--host", choices=("codex", "claude"), default=None)
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
    codex_config_path = resolve_codex_config_arg(args.host, args.codex_config, "plan")
    effective_config_path = codex_config_path or (root / ".sos-no-codex-config")
    out = Path(args.out)
    skills = scan_skill_roots(
        (root,),
        disabled_paths=disabled_paths_from_config(codex_config_path),
    )
    proposals = propose_builtin_packs(skills)
    plan = build_pack_apply_plan(
        runtime_paths, root, effective_config_path, proposals, host=args.host
    )
    serialize_write_plan(plan, out)
    print(f"write plan: {out}")
    print(summarize_write_plan(plan))
    return 0


def _handle_apply(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = load_write_plan(plan_path)
    host = args.host or plan.host
    if args.host is not None and args.host != plan.host:
        raise ValueError(
            f"plan host {plan.host!r} does not match --host {args.host!r}"
        )
    context = context_from_plan(plan, host)
    _validate_delete_source_args(args)
    result = apply_write_plan(
        plan,
        context["runtime_paths"],
        context["codex_config_path"],
        context["active_skill_root"],
        apply=bool(args.apply),
        host=host,
        delete_source=bool(args.delete_source),
        confirm_delete_source=args.confirm_delete_source,
    )
    if not args.apply:
        print("dry-run apply; no external files written")
        print(summarize_write_plan(plan))
        return 0
    if result.backup_id:
        annotate_backup_metadata(
            context["runtime_paths"],
            result.backup_id,
            codex_config_path=context["codex_config_path"],
            active_skill_root=context["active_skill_root"],
            host=host,
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
    codex_config_path = resolve_codex_config_arg(args.host, args.codex_config, "changes")
    report = detect_changes(root, runtime_paths, codex_config_path)
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
    if args.host == "codex":
        print("- disable managed source skills in Codex config if they should stay vault-managed")
    else:
        print("- move unexpectedly enabled source skills into .sos-archive/ via a Claude apply")
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
    codex_config_path, vault_root = restore_targets(runtime_paths, args.backup_id)
    codex_display = str(codex_config_path) if codex_config_path is not None else "(no codex config)"
    vault_display = str(vault_root) if vault_root is not None else "(no vault target)"
    if not args.apply:
        print("dry-run restore; no external files written")
        print(f"backup_id: {args.backup_id}")
        print(f"codex_config_path: {codex_display}")
        print(f"vault_root: {vault_display}")
        return 0
    record = restore_backup(
        runtime_paths,
        args.backup_id,
        codex_config_path,
        vault_root,
        apply=True,
    )
    print(f"restored: {record.backup_id}")
    print(f"codex_config_path: {codex_display}")
    print(f"vault_root: {vault_display}")
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
    print(f"manifest_fingerprint: {runtime_manifest_fingerprint(runtime_paths)}")
    print(
        "learned_reference: "
        + ("present" if learned_path.is_file() else "missing")
    )
    print(f"learned_reference_path: {redacted_runtime_path(learned_path, runtime_paths)}")
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
        host=args.host,
    )
    serialize_write_plan(plan, out)
    print("workspace activation plan: WORKSPACE_PLAN")
    print(
        redacted_recommendation_plan_summary(
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
        host=args.host,
    )
    if not args.apply:
        print("dry-run workspace activation; no external files written")
        print(
            redacted_recommendation_plan_summary(
                plan,
                runtime_paths,
                args.workspace_root,
                plan_path=Path(args.plan),
            )
        )
        return 0
    print(f"apply status: {result.status}")
    if result.backup_id:
        print(f"backup_id: {result.backup_id}")
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
    validate_scenario_label_argument(args.scenario_label, scenario_tags)
    scenario_tags = canonicalize_scenario_tags(scenario_tags)
    selected_pack_ids, selected_skill_names = validate_recommendation_selection(
        runtime_paths,
        selected_pack_ids,
        selected_skill_names,
    )
    current_manifest_fingerprint = runtime_manifest_fingerprint(runtime_paths)
    if args.manifest_fingerprint != current_manifest_fingerprint:
        raise ValueError("manifest fingerprint does not match current runtime manifests")
    event = SelectionEvent(
        schema_version=1,
        created_at=_utc_now_isoformat(),
        workspace_id=workspace_id_for_path(args.workspace_root),
        scenario_label=scenario_label_from_tags(scenario_tags),
        scenario_tags=scenario_tags,
        selected_pack_ids=selected_pack_ids,
        selected_skill_names=selected_skill_names,
        manifest_fingerprint=current_manifest_fingerprint,
        selection_source="user_accepted",
        outcome="activated",
    )
    path = append_selection_event(runtime_paths, event)
    print(f"selection event: {redacted_runtime_path(path, runtime_paths)}")
    print(
        "recorded selection: "
        f"{event.scenario_label}; packs={', '.join(event.selected_pack_ids)}; "
        f"skills={', '.join(event.selected_skill_names)}"
    )
    return 0


def _handle_recommend_learn(args: argparse.Namespace) -> int:
    runtime_paths = RuntimePaths.from_root(args.runtime_root)
    reference = build_learned_reference(
        manifest_valid_selection_events(
            load_selection_events(runtime_paths),
            runtime_paths,
        )
    )
    path = write_learned_reference(runtime_paths, reference, apply=bool(args.apply))
    if not args.apply:
        print("learned reference preview:")
        print(reference.rstrip())
        print(f"path: {redacted_runtime_path(path, runtime_paths)}")
        return 0
    print(f"learned reference: applied {redacted_runtime_path(path, runtime_paths)}")
    return 0


def _scan_from_args(
    root: str | Path,
    codex_config_path: str | Path | None,
) -> tuple[ScannedSkill, ...]:
    return scan_skill_roots(
        (Path(root),),
        disabled_paths=disabled_paths_from_config(codex_config_path),
    )


def _validate_delete_source_args(args: argparse.Namespace) -> None:
    if args.confirm_delete_source is not None and not args.delete_source:
        raise ValueError("--confirm-delete-source requires --delete-source")
    if args.delete_source and not args.apply:
        raise ValueError("--delete-source requires --apply")
    if args.delete_source and args.confirm_delete_source is None:
        raise ValueError("--delete-source requires --confirm-delete-source")


def _manifest_path(runtime_paths: RuntimePaths, pack_id: str) -> Path:
    safe_component(pack_id, "pack")
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


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat()
