# SOS Workflows

Use these workflows as routing guides. Replace uppercase argument names such as `SKILLS_ROOT` and `RUNTIME_ROOT` with paths confirmed from the user or from `scripts/sos_doctor.py`.

## Inspect Active Skills

Start with scan. This is read-only.

```text
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

## Propose Packs

Use propose to generate reviewable pack candidates. This is read-only.

```text
sos propose --root SKILLS_ROOT
```

## Create A Reviewable Plan

Plan writes only the explicit plan file. Confirm the output path first.

```text
sos plan --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH
```

## Dry-Run Apply

Run apply without `--apply` first.

```text
sos apply --plan PLAN_PATH
```

## Apply A Reviewed Plan

Before applying, read `safety-model.md` and get explicit human approval.

```text
sos apply --plan PLAN_PATH --apply
```

## Activate A Pack

Pack activation may sync clean source changes into the vault. Explain that activation is part of managed routing.

```text
sos pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto
```

## Check Status And Backups

Status and backup list are read-only.

```text
sos status --runtime-root RUNTIME_ROOT
sos backup list --runtime-root RUNTIME_ROOT
```

## Restore

Run restore as a dry run before applying.

```text
sos restore BACKUP_ID --runtime-root RUNTIME_ROOT
sos restore BACKUP_ID --runtime-root RUNTIME_ROOT --apply
```
