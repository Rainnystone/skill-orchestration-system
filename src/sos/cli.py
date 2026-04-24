from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sos import __version__
from sos.apply import apply_write_plan
from sos.backups import list_backups, prune_backups, restore_backup
from sos.codex_config import load_codex_config
from sos.manifest import load_registry
from sos.models import OperationKind, WriteOperation, WritePlan
from sos.paths import RuntimePaths
from sos.planner import (
    build_pack_apply_plan,
    load_write_plan,
    serialize_write_plan,
    summarize_write_plan,
)
from sos.propose import propose_builtin_packs
from sos.scanner import ScannedSkill, scan_skill_roots
from sos.sync import activate_pack, apply_pack_sync, plan_pack_sync
from sos.toml_io import read_toml, write_toml


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

    status = subcommands.add_parser("status", help="summarize runtime status")
    status.add_argument("--runtime-root", required=True)
    status.set_defaults(handler=_handle_status)

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
