# SOS Workflows

Use these workflows as routing guides. Replace uppercase argument names such as `SKILLS_ROOT` and `RUNTIME_ROOT` with paths confirmed from the user or from `scripts/sos_doctor.py`.

## Resolve Invocation First

Before using any workflow below, run or inspect `scripts/sos_doctor.py` and read `execution-modes.md` when capability is uncertain. Choose one invocation mode:

- Advisory mode: do not run SOS commands; explain the missing backend.
- Repo-local mode: use the repo-local Python invocation reported by the doctor with its `env_updates`.
- Installed-CLI mode: use the installed CLI invocation reported by the doctor.

The command blocks below are workflow arguments. First remove the doctor check argument such as `--version`, then append the workflow arguments to the selected invocation shape. They do not prove that a global `sos` executable exists and must not be presented as requiring global installation.

## Inspect Active Skills

Start with scan. This is read-only.

```text
scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

## Propose Packs

Use propose to generate reviewable pack candidates. This is read-only.

```text
propose --root SKILLS_ROOT
```

## Create A Reviewable Plan

Plan writes only the explicit plan file. Confirm the output path first.

```text
plan --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH
```

## Dry-Run Apply

Run apply without `--apply` first.

```text
apply --plan PLAN_PATH
```

## Apply A Reviewed Plan

Before applying, read `safety-model.md` and get explicit human approval.

```text
apply --plan PLAN_PATH --apply
```

## Activate A Pack

Pack activation may sync clean source changes into the vault. Before activation, read `safety-model.md`, show read-only context with status and backup list when available, and get explicit human approval before running `pack activate`.

```text
status --runtime-root RUNTIME_ROOT
backup list --runtime-root RUNTIME_ROOT
pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto
```

## Check Status And Backups

Status and backup list are read-only.

```text
status --runtime-root RUNTIME_ROOT
backup list --runtime-root RUNTIME_ROOT
```

## Restore

Run restore as a dry run before applying.

```text
restore BACKUP_ID --runtime-root RUNTIME_ROOT
restore BACKUP_ID --runtime-root RUNTIME_ROOT --apply
```
