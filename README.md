# Skill Orchestration System

[English](README.md) | [中文](README_CN.md)

Your agent skills should feel like a sharp toolbox, not a second junk drawer.

Skill Orchestration System, or SOS, helps Codex users organize a growing local
skill library into small, reviewable, activatable packs. It keeps the active
surface area tidy, writes plans before it writes files, and gives you a way back
when an experiment does not deserve to become permanent.

SOS is Codex-first today. Claude Code compatibility is kept as a structural
opening, but Claude-specific integration is not wired up yet.

## Why SOS Exists

Agent skills are powerful because they are easy to add. That is also the
problem.

After a while, your skills folder can turn into a pile of half-related tools:
old experiments, one-off workflows, plugin cache copies, personal helpers,
generated pointers, and a few actually-important skills buried somewhere in the
middle. Loading too much at once makes agents harder to steer. Moving files by
hand is easy until a config write, backup, or rollback path is missed.

SOS gives that mess a boring, useful shape:

- scan local `SKILL.md` folders;
- propose task-focused skill packs;
- write a plan before changing anything important;
- copy selected skills into a managed vault;
- generate short active pointer skills such as `sos-<pack>`;
- keep manifests, registry state, fingerprints, and backups;
- restore or inspect state when you need to unwind.

The goal is not to make skills fancy. The goal is to make them usable again.

## The Short Version

SOS has two layers:

- a **Codex skill wrapper** in `.agents/skills/sos/`, designed for guided,
  no-global-install workflows;
- a **Python CLI backend** in `src/sos/`, which performs deterministic scanning,
  planning, applying, syncing, backup, and restore behavior.

The skill helps the agent decide what to do next. The CLI does the file work.
That split matters: prompts can guide, but writes should stay deterministic.

## Start Without A Global Install

The recommended first path is to use the bundled `sos` skill from this
repository. You can clone the repo, open it in Codex, and ask Codex to use the
SOS skill to inspect or organize your local skills.

```bash
git clone https://github.com/Rainnystone/skill-orchestration-system.git
cd skill-orchestration-system
```

Then ask Codex something like:

```text
Use the sos skill to inspect my local skills and suggest a safe plan.
```

The skill will start by checking what can run locally. You can also run the
doctor directly:

```bash
python .agents/skills/sos/scripts/sos_doctor.py --no-path-lookup
```

If the source checkout is available, SOS can run in repo-local mode without
installing a global `sos` command.

**macOS / Linux:**

```bash
PYTHONPATH=src python -m sos --version
```

**Windows PowerShell:**

```powershell
$env:PYTHONPATH = "src"
python -m sos --version
```

Expected output:

```text
sos 0.1.0
```

## Install For Development

If you want a normal editable Python install for development, use Python 3.11 or
newer.

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m sos --version
```

After installation, the console script is also available:

```bash
sos --version
```

## How To Use SOS

There are two ways to use SOS.

### Codex Skill Path

This is the intended first-run path. Keep this repository available in a Codex
workspace, then ask Codex to use the bundled `sos` skill. You do not need to
memorize the command sequence.

Useful prompts:

```text
Use the sos skill to inspect my local Codex skills and explain what it finds.
Use the sos skill to propose skill packs, but do not write anything yet.
Use the sos skill to create a dry-run plan for organizing my skills.
Use the sos skill to apply the reviewed plan.
Use the sos skill to show what is inside my current packs.
Use the sos skill to check what changed after I installed new skills.
```

When the skill activates, Codex reads `.agents/skills/sos/SKILL.md`, runs or
inspects `sos_doctor.py`, chooses repo-local mode or installed-CLI mode, asks
for missing paths, and then uses dry-run-first SOS commands.

### CLI Path

The CLI is what the skill calls when it needs deterministic file work. If SOS is
installed, the command shape is:

```bash
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

Without a global install, use the same command through the source checkout:

**macOS / Linux:**

```bash
PYTHONPATH=src python -m sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

**Windows PowerShell:**

```powershell
$env:PYTHONPATH = "src"
python -m sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

So yes, the old shape is still there: the product command family is `sos ...`.
`python -m sos ...` is just the no-global-install way to run that same backend
from the repo.

### After You Apply A Plan

SOS writes active pointer skills into the skills root you selected:

- `sos-haruhi` manages SOS status, backups, restores, and pack operations;
- `sos-<pack>` points to one generated skill pack, for example `sos-writing` if
  the pack id is `writing`.

Then you use those generated skills like normal Codex skills:

```text
Use sos-haruhi to show my SOS status.
Use sos-writing for this documentation task.
```

A pack pointer runs
`sos pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto` before
reading the managed vault copy. That is how SOS keeps the active skill layer
small while still preserving the full skill content in the vault.

### Seeing What Is Inside A Pack

Once packs exist, you do not have to guess what an agent will see. Ask the
`sos` skill, or run the read-only CLI commands directly:

```bash
sos pack list --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

`pack list` answers "what packs do I have?" `pack show` answers "what skills
are inside this pack?" If you name a skill, SOS filters the manifest to that
exact skill name so the agent can read one vault skill instead of browsing the
whole pack up front.

### After You Install Or Edit Skills

When your local skill library changes, use `changes` before creating a new plan:

```bash
sos changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG
```

This is also read-only. It reports new unmanaged skills, missing or changed
managed sources, vault drift, missing or stale generated pointers, and managed
source skills that were unexpectedly re-enabled. It does not apply repairs; it
only tells you what deserves a new scan, proposal, or reviewed plan.

### Workspace Recommendation Path

SOS also has a workspace-level recommendation flow for "what should this
workspace enable right now?" without turning that choice into a global skill
change.

- `sos-nagato` is the workspace recommender. It inspects the current workspace,
  reads the local learned reference when it exists, and suggests relevant
  managed packs.
- `sos-asahina` is not an automatic recommender. Use it only when you want to
  explicitly organize approved recommendation outcomes into a learned reference.

The flow stays local and reviewable:

1. Inspect the workspace without writing anything:

   ```bash
   sos recommend context --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
   ```

2. Write a reviewable workspace activation plan:

   ```bash
   sos recommend activation-plan --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
   ```

3. Preview the plan:

   ```bash
   sos recommend activate --plan WORKSPACE_PLAN --runtime-root RUNTIME_ROOT
   ```

4. Apply only after review:

   ```bash
   sos recommend activate --plan WORKSPACE_PLAN --runtime-root RUNTIME_ROOT --apply
   ```

When applied, SOS writes workspace-only skills into
`WORKSPACE_ROOT/.agents/skills/`:

- `sos-nagato/SKILL.md`
- `sos-asahina/SKILL.md`
- one `sos-<pack>/SKILL.md` pointer for each selected pack

Recommendation state is stored under
`RUNTIME_ROOT/state/recommendations/`:

- `selection-events.jsonl` stores accepted selection records
- `asahina-reference.md` stores the learned reference used by `sos-nagato`

This recommendation flow does not write global skills, does not use hooks, and
does not store raw prompts, file contents, model messages, account identifiers,
or broad private absolute paths. The stored workspace identifier is a hash, so
review logs remain auditable without exposing the original workspace path.

## A Safe First Workflow

The exact paths depend on your machine. In the examples below, replace:

- `SKILLS_ROOT` with your active Codex skills directory;
- `RUNTIME_ROOT` with the SOS runtime directory you want to use;
- `CODEX_CONFIG` with your Codex config path;
- `PLAN_PATH` with the plan file path you want SOS to write.

Inspect first:

```bash
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
sos propose --root SKILLS_ROOT
```

Create a reviewable plan:

```bash
sos plan --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH
```

Dry-run the plan:

```bash
sos apply --plan PLAN_PATH
```

Only after reviewing the plan:

```bash
sos apply --plan PLAN_PATH --apply
```

## Safety Model

SOS is intentionally conservative.

- `scan` and `propose` do not write.
- `plan` writes only the explicit plan file.
- `apply` without `--apply` is a dry run.
- `apply --apply` creates backups before managed writes.
- source skill deletion is off by default and requires `--delete-source`,
  `--apply`, and `--confirm-delete-source <pack-id>`;
- restore and backup cleanup are dry-run by default unless `--apply` is used.

Review the plan before running anything that writes. If in doubt, run the dry
run again.

## What SOS Creates

When an approved plan is applied, SOS writes generated active skills into the
skill root you chose. The generated entry points are intentionally short:

- `sos-haruhi`: a companion skill for pack management, status, backup, and
  restore workflows;
- `sos-<pack>`: one pointer skill per pack.

Pointer skills do not embed the full original skill body. They point the agent
to the pack manifest and the managed vault copy. When the user names a packed
skill, the pointer matches that name against manifest `skills.name`; otherwise
it chooses from manifest `skills.name` and `skills.description`, and asks when
the choice is ambiguous. That keeps the active layer small and keeps detailed
skill content where it belongs.

## How It Works

```text
.
|-- .agents/skills/sos/     # Codex-facing SOS skill wrapper
|-- references/             # Public behavior and safety references
|-- src/sos/                # CLI and library implementation
|   |-- cli.py              # Command-line entry point
|   |-- scanner.py          # SKILL.md discovery
|   |-- propose.py          # Pack proposal rules
|   |-- pack_inspect.py     # Read-only pack list/show helpers
|   |-- changes.py          # Read-only runtime and skill drift reporting
|   |-- planner.py          # Reviewable write-plan generation
|   |-- apply.py            # Plan execution and rollback-aware writes
|   |-- sync.py             # Pack activation and clean sync behavior
|   |-- backups.py          # Backup, restore, and retention helpers
|   `-- templates/          # Packaged pointer skill templates
|-- templates/              # Source copies of generated-skill templates
|-- tests/                  # Unit tests and CLI smoke tests
|-- README.md               # English README
|-- README_CN.md            # Chinese README
|-- pyproject.toml          # Python package metadata
`-- LICENSE
```

A typical SOS runtime root looks like this:

```text
<runtime-root>/
  backups/
  packs/
  state/
  vault/
```

- `vault/` stores managed skill copies.
- `packs/` stores TOML pack manifests, including each managed skill's
  `name`, `description`, source path, vault path, and sync fingerprints.
- `state/` stores registry state.
- `backups/` stores config and vault snapshots created before writes.

Pack proposals are deterministic. SOS first looks at Agent Skill head metadata,
especially `name` and `description`, and prefers clear source/tool families such
as Apify or Obsidian before functional groups such as Docs, Browser, Deploy, or
Data. Ambiguous skills are left for human review instead of being packed by a
hidden classifier.

## CLI Reference

| Command | Purpose | Writes by default |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | List enabled skills under a root. | No |
| `sos propose --root <path>` | Propose pack candidates from scanned skills. | No |
| `sos plan --root <path> --runtime-root <path> --codex-config <path> --out <path>` | Write a reviewable plan file. | Only the plan file |
| `sos apply --plan <path>` | Summarize a plan. | No |
| `sos apply --plan <path> --apply` | Copy skills, write manifests and pointers, disable originals, and create backups. | Yes |
| `sos pack activate <pack> --runtime-root <path>` | Activate a pack and apply eligible clean syncs. | Sometimes |
| `sos pack list --runtime-root <path>` | List written runtime packs. | No |
| `sos pack show <pack> --runtime-root <path>` | Show one pack manifest and its managed skills. | No |
| `sos pack sync <pack> --runtime-root <path>` | Show a pack sync plan. | No |
| `sos pack sync <pack> --runtime-root <path> --apply` | Apply a valid pack sync plan. | Yes |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | Report new, missing, changed, stale, or unexpectedly enabled skills and pointers. | No |
| `sos status --runtime-root <path>` | Show runtime registry and backup state. | No |
| `sos backup list --runtime-root <path>` | List backups. | No |
| `sos backup clean --runtime-root <path> --keep <count>` | Preview backup pruning. | No |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | Prune old backups. | Yes |
| `sos restore <backup-id> --runtime-root <path>` | Preview restore targets. | No |
| `sos restore <backup-id> --runtime-root <path> --apply` | Restore recorded config and vault targets. | Yes |

## Compatibility

SOS is Codex-first. Its tested write path can update Codex skill configuration
after creating backups and only when `--apply` is used.

Claude Code compatibility is structural for now: generated skills are ordinary
`SKILL.md` folders, and pack metadata is stored in plain TOML manifests. SOS
does not yet provide a Claude Code installer, settings writer, or integration
test suite.

## Development

Run tests:

```bash
python -m pytest
```

Run the source-tree CLI smoke check:

```bash
PYTHONPATH=src python -m sos --version
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m sos --version
```

## Project Status

SOS is early software. The implemented behavior is covered by tests, but the
public API and pack proposal model may evolve before a stable release.

## Security And Privacy

Do not commit real local config files, private skill libraries, backups, runtime
vault contents, account data, or tokens. When sharing bug reports, replace local
paths, usernames, and private workspace names with placeholders.

## License

MIT License. See [LICENSE](LICENSE).
