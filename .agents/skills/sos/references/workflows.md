# SOS Workflows

Use these workflows as routing guides. Replace uppercase argument names such as `SKILLS_ROOT` and `RUNTIME_ROOT` with paths confirmed from the user or from `scripts/sos_doctor.py`.

## Resolve Invocation First

Before using any workflow below, run or inspect `scripts/sos_doctor.py` and read `execution-modes.md` when capability is uncertain. Choose one invocation mode:

- Advisory mode: do not run SOS commands; explain the missing backend.
- Repo-local mode: use the repo-local Python invocation reported by the doctor with its `env_updates`.
- Installed-CLI mode: use the installed CLI invocation reported by the doctor.

The command blocks below are workflow arguments. First remove the doctor check argument such as `--version`, then append the workflow arguments to the selected invocation shape. They do not prove that a global `sos` executable exists and must not be presented as requiring global installation.

## Resolve Host First

Before any write command, confirm the target host:

- `--host codex`: write goes to `~/.codex/skills` or the path the user names. Apply disables skills by writing `enabled = false` in Codex config.
- `--host claude`: write goes to `~/.claude/skills` or `.claude/skills`. Apply disables skills by moving the original folder to `<skill-root>/.sos-archive/<pack-id>/<name>/`.

The doctor reports a `claude_skill_root` field when `~/.claude/skills` or
`<cwd>/.claude/skills` exists. Surface it to the user; do not assume.

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

## Draft Pack Head Text

When a pack proposal needs better agent routing, Codex may draft a short Pack Head from the selected skills' `name` and `description` fields. Treat it like an Agent Skill description: what the pack helps with, in terms the user may say.

The draft must be part of a reviewable plan before SOS writes it. The SOS CLI must not call a model or silently rewrite the pack head during sync.

## Inspect Packs

Pack inspection is read-only. Use it to inspect pack metadata before reading vault skill bodies.

```text
pack list --runtime-root RUNTIME_ROOT
pack show PACK_ID --runtime-root RUNTIME_ROOT
pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

## Detect New Or Changed Skills

Use changes when the user says they installed, removed, updated, or re-enabled skills. This is read-only.

```text
# Codex
changes --host codex --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG

# Claude (no --codex-config)
changes --host claude --root SKILLS_ROOT --runtime-root RUNTIME_ROOT
```

## Select A Skill Inside A Pack

Inspect the manifest first. If the user names a skill, match it exactly against manifest `skills.name`. If exactly one skill matches, state the selected vault skill and why it was selected, then read only that selected vault skill's `SKILL.md`. If the user did not name a skill, choose from manifest `skills.name` and `skills.description`, and ask if the choice is ambiguous.

```text
pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

## Create A Reviewable Plan

Plan writes only the explicit plan file. Confirm the output path first.

```text
# Codex
plan --host codex --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH

# Claude (no --codex-config)
plan --host claude --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --out PLAN_PATH
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
