# SOS: Make Vibe Coding More Lively

[English](README.md) | [中文](README_CN.md)

Your agent skills should feel like a capable club room, not a storage closet
where every old experiment has somehow earned permanent residency.

Skill Orchestration System, or SOS, helps Codex and Claude Code users keep a
growing local skill library organized. It scans local Agent Skills, proposes
task-focused packs, writes reviewable plans before touching important files, and
keeps rollback paths nearby. A shocking idea, I know: let the strange club do
the paperwork before it rearranges the furniture.

SOS supports Codex and Claude Code. Use `--host {codex,claude}` to select the
host per write command.

## Why You Need SOS

Agent skills are easy to add. That is useful, right up until your skills folder
starts looking like a group project nobody volunteered to clean.

After a few weeks, you may have old experiments, one-off workflows, plugin cache
copies, personal helpers, and the few skills you actually need all living in the
same place. If every skill stays active, the agent sees too much. If you move
files by hand, you eventually miss a config entry, a backup, or a rollback path.
Neither outcome is exactly the glorious future promised by vibe coding.

SOS gives that sprawl a small, auditable shape:

- scan local `SKILL.md` folders;
- propose focused packs such as docs, browser, data, deploy, or tool-specific
  groups;
- write a dry-run plan before managed writes;
- copy selected skills into a managed vault;
- generate short active skills such as `sos-haruhi` and `sos-<pack>`;
- keep manifests, registry state, fingerprints, backups, and restore paths;
- recommend workspace-level packs through `sos-nagato` when one workspace needs
  a different setup from another.

The point is not to make your skill system mysterious. The point is to keep the
mystery where it belongs: in what you are building, not in which folder contains
the correct `SKILL.md`.

## How To Use SOS

There are three practical paths: use the bundled Codex skill, use the CLI
directly, or use workspace recommendation when a specific project needs a
temporary skill set.

### Codex Skill Path

This is the intended first path. Open this repository in Codex and ask Codex to
use the bundled `sos` skill.

Useful prompts:

```text
Use the sos skill to inspect my local Codex skills and explain what it finds.
Use the sos skill to propose skill packs, but do not write anything yet.
Use the sos skill to create a dry-run plan for organizing my skills.
Use the sos skill to apply the reviewed plan.
Use the sos skill to show what is inside my current packs.
Use the sos skill to check what changed after I installed new skills.
```

The skill checks whether SOS can run from the current checkout or from an
installed CLI, asks for missing paths, then uses dry-run-first commands. The
skill guides the conversation; deterministic Python code performs the file work.

### CLI Path

The CLI is the backend the skill calls. If SOS is installed, commands look like
this:

```bash
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
sos propose --root SKILLS_ROOT
sos plan --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH
sos apply --plan PLAN_PATH
sos apply --plan PLAN_PATH --apply
```

The safe rhythm is always the same:

1. `scan` and `propose` inspect.
2. `plan` writes only a plan file.
3. `apply` without `--apply` previews.
4. `apply --apply` writes managed files after you review the plan.

### Use Generated Pack Skills

After a plan is applied, SOS writes short active skills into the selected skills
root:

- `sos-haruhi` for SOS status, pack management, backups, restores, and changes;
- `sos-<pack>` for each generated pack, such as `sos-docs` or `sos-browser`.

Use them like normal Codex skills:

```text
Use sos-haruhi to show my SOS status.
Use sos-docs for this documentation task.
Use sos-browser to inspect this local web flow.
```

Pack pointers do not paste the entire original skill body into the active layer.
They point the agent to the pack manifest and managed vault copy. If you name a
specific packed skill, SOS matches it against manifest `skills.name`; otherwise
the pointer chooses from manifest metadata and asks when the choice is unclear.
Before reading the vault copy, a pack pointer uses
`pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto` so the
managed copy can stay current.

### Inspect Existing Packs

When you want to know what is inside the club room before someone starts issuing
orders:

```bash
sos pack list --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

These commands are read-only. They answer what packs exist, which skills are in
each pack, and where the managed vault copies live.

### Check Drift After Installing Or Editing Skills

If your local skill library changes, run:

```bash
sos changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG
```

It reports new unmanaged skills, missing or changed managed sources, vault
drift, stale pointers, and managed source skills that were unexpectedly enabled.
It does not repair anything by itself. It just points at the problem and waits,
which is more restraint than some fictional club presidents might show.

### Use Workspace Recommendations

Some workspaces need their own active skills without changing your global skill
setup. That is where the Haruhi-themed pair comes in.

- `sos-nagato` recommends workspace-level packs. It inspects lightweight
  workspace signals, reads the local learned reference if one exists, and
  suggests relevant managed packs.
- `sos-asahina` is explicit. Use it when you want to turn approved local
  recommendation history into a learned reference for future `sos-nagato`
  recommendations. It is not a hook and it does not run in the background.

Typical flow:

```bash
sos recommend context --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activation-plan --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
sos recommend activate --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activate --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
```

After successful workspace activation, SOS writes workspace-only skills under:

```text
WORKSPACE_ROOT/.agents/skills/
```

That includes:

- `sos-nagato/SKILL.md`
- `sos-asahina/SKILL.md`
- one `sos-<pack>/SKILL.md` pointer for each selected pack

If the user accepts the recommendation, record that local fact:

```bash
sos recommend record-selection --runtime-root RUNTIME_ROOT --workspace-root WORKSPACE_ROOT --scenario-label docs --scenario-tags docs --packs docs --skills documents --manifest-fingerprint sha256:example
```

When you explicitly want to refresh the learned reference:

```bash
sos recommend learn --runtime-root RUNTIME_ROOT
sos recommend learn --runtime-root RUNTIME_ROOT --apply
```

`learn` validates historical records against the current runtime manifests
before using them. Stale local records or hand-edited JSONL that no longer match
real packs and skills are skipped.

## How To Install SOS

### Try It Without A Global Install

Clone the repository:

```bash
git clone https://github.com/Rainnystone/skill-orchestration-system.git
cd skill-orchestration-system
```

Then ask Codex:

```text
Use the sos skill to inspect my local skills and suggest a safe plan.
```

You can also run the doctor directly:

```bash
python .agents/skills/sos/scripts/sos_doctor.py --no-path-lookup
```

Run the source-tree CLI smoke check:

**macOS / Linux**

```bash
PYTHONPATH=src python -m sos --version
```

**Windows PowerShell**

```powershell
$env:PYTHONPATH = "src"
python -m sos --version
```

Expected output:

```text
sos 0.1.0
```

### Install For Development

Use Python 3.11 or newer.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m sos --version
```

After installation, the console script is available:

```bash
sos --version
```

### Claude Code Host

Claude Code uses the same scan, plan, dry-run, apply rhythm, because apparently
one club can have more than one doorway. Use `--host claude`; the skill root is
usually `~/.claude/skills`, or `.claude/skills` inside a project workspace.

```bash
sos scan --root ~/.claude/skills
sos propose --root ~/.claude/skills
sos plan --host claude --root ~/.claude/skills --runtime-root ~/.sos --out plan.toml
sos apply --plan plan.toml
sos apply --plan plan.toml --host claude --apply
```

For `sos plan` and `sos changes`, `--codex-config` is required when
`--host codex` and rejected when `--host claude`. `sos apply` reads the host
from the plan TOML, so apply commands do not take `--codex-config` directly.
After apply, disabled Claude source skills move under
`~/.claude/skills/.sos-archive/<pack-id>/<name>/`; restore moves them back.

## Technical Reference

### Safety Model

SOS is intentionally conservative.

- `scan`, `propose`, `pack list`, `pack show`, `changes`, `status`, and most
  preview commands do not write.
- `plan` writes only the explicit plan file.
- `apply` without `--apply` is a dry run.
- `apply --apply` creates backups before managed writes.
- source skill deletion is off by default and requires `--delete-source`,
  `--apply`, and `--confirm-delete-source <pack-id>`.
- restore and backup cleanup are dry-run by default unless `--apply` is used.
- workspace recommendation activation requires an explicit `--workspace-root`
  anchor, so a tampered plan cannot silently redirect workspace skill writes.

### What SOS Creates

An approved global plan writes generated active skills into the skill root you
choose. A workspace recommendation plan writes generated skills only into that
workspace's `.agents/skills/` directory.

The generated entry points are intentionally short:

- `sos-haruhi`: companion skill for pack management and SOS operations;
- `sos-nagato`: workspace recommender;
- `sos-asahina`: explicit learned-reference helper;
- `sos-<pack>`: one pointer skill per selected pack.

Pointer skills do not embed full source skill bodies. They route the agent to
manifests and vault copies so the active skill surface stays small.

### Runtime Layout

```text
<runtime-root>/
  backups/
  packs/
  state/
  vault/
```

- `vault/` stores managed skill copies.
- `packs/` stores TOML pack manifests.
- `state/` stores registry and recommendation state.
- `backups/` stores config and vault snapshots created before writes.

Workspace recommendation state lives under:

```text
<runtime-root>/state/recommendations/
  selection-events.jsonl
  asahina-reference.md
```

Records stay local. SOS stores compact scenario tags, selected pack ids,
selected skill names, a manifest fingerprint, and a hashed workspace id. It does
not store raw prompts, file contents, model messages, account identifiers, or
broad private absolute paths.

### Project Layout

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
|   |-- workspace_activation.py
|   |-- recommendation_engine.py
|   |-- recommendation_store.py
|   `-- templates/          # Packaged generated-skill templates
|-- templates/              # Source copies of generated-skill templates
|-- tests/                  # Unit tests and CLI smoke tests
|-- README.md
|-- README_CN.md
|-- pyproject.toml
`-- LICENSE
```

### CLI Reference

| Command | Purpose | Writes by default |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | List enabled skills under a root. | No |
| `sos propose --root <path>` | Propose pack candidates from scanned skills. | No |
| `sos plan --host <host> --root <path> --runtime-root <path> --codex-config <path> --out <path>` | Write a reviewable plan file. | Only the plan file |
| `sos apply --plan <path> [--host <host>]` | Summarize a plan; host inferred from plan when omitted. | No |
| `sos apply --plan <path> [--host <host>] --apply` | Copy skills, write manifests and pointers, disable originals (Codex: config write; Claude: move to `.sos-archive`), and create backups. | Yes |
| `sos pack activate <pack> --runtime-root <path>` | Activate a pack and apply eligible clean syncs. | Sometimes |
| `sos pack list --runtime-root <path>` | List runtime packs. | No |
| `sos pack show <pack> --runtime-root <path>` | Show one pack manifest and its managed skills. | No |
| `sos pack sync <pack> --runtime-root <path>` | Show a pack sync plan. | No |
| `sos pack sync <pack> --runtime-root <path> --apply` | Apply a valid pack sync plan. | Yes |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | Report new, missing, changed, stale, or unexpectedly enabled skills and pointers. | No |
| `sos recommend context --workspace-root <path> --runtime-root <path>` | Inspect workspace recommendation context. | No |
| `sos recommend activation-plan --workspace-root <path> --runtime-root <path> --packs <ids> --out <path>` | Write a workspace activation plan. | Only the plan file |
| `sos recommend activate --plan <path> --workspace-root <path> --runtime-root <path>` | Preview workspace activation. | No |
| `sos recommend activate --plan <path> --workspace-root <path> --runtime-root <path> --apply` | Write workspace skills and the learned-reference stub. | Yes |
| `sos recommend record-selection --runtime-root <path> --workspace-root <path> ...` | Record one accepted workspace recommendation selection. | Yes |
| `sos recommend learn --runtime-root <path>` | Preview the learned reference. | No |
| `sos recommend learn --runtime-root <path> --apply` | Write the learned reference. | Yes |
| `sos status --runtime-root <path>` | Show runtime registry and backup state. | No |
| `sos backup list --runtime-root <path>` | List backups. | No |
| `sos backup clean --runtime-root <path> --keep <count>` | Preview backup pruning. | No |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | Prune old backups. | Yes |
| `sos restore <backup-id> --runtime-root <path>` | Preview restore targets. | No |
| `sos restore <backup-id> --runtime-root <path> --apply` | Restore recorded config and vault targets. | Yes |

### Compatibility

SOS supports two hosts:

- **Codex**: write path updates Codex skill configuration after creating backups and only when `--apply` is used.
- **Claude Code**: write path moves disabled source folders into `<skill-root>/.sos-archive/<pack-id>/<name>/` so Claude no longer discovers them, after creating a vault backup and only when `--apply` is used.

Generated skills are ordinary `SKILL.md` folders, and pack metadata is stored in plain TOML manifests. The host is selected per write command via `--host {codex,claude}`.

### Development

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

### Project Status

SOS is early software. The implemented behavior is covered by tests, but the
public API and pack proposal model may evolve before a stable release.

### Security And Privacy

Do not commit real local config files, private skill libraries, backups, runtime
vault contents, account data, or tokens. When sharing bug reports, replace local
paths, usernames, and private workspace names with placeholders.

## License

MIT License. See [LICENSE](LICENSE).
