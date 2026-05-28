# SOS: Make Vibe Coding More Lively

[English](README.md) | [中文](README_CN.md)

> Good grief. Your agent skills should feel like a capable, tidy club room, not a storage closet where every discarded experiment has somehow earned permanent residency.
> Why does almost every AI Agent framework assume the solution to a complex task is to dump dozens of tools into the prompt context at once?
> You start vibe-coding, and within three days, your active skills folder looks exactly like the SOS Brigade clubroom—cluttered with strange, useless gadgets a certain chaotic "Brigade Chief" dragged in from who-knows-where.
> If you leave them all active, the Agent gets cross-eyed and response times crawl. If you move directories by hand, you are bound to miss a config file, a backup, or a rollback path.
> Since we've already been dragged into this bizarre club's workflow, we might as well handle it the rational way. Let's establish some basic paperwork rules to keep the chief's chaotic tool cabinet looking semi-professional.

---

## 🔍 What is SOS?

**Skill Orchestration System (SOS)** is a lightweight local Agent Skill manager and dynamic routing registry designed for **Codex** and **Claude Code**.

By utilizing a **Skill Pack (Vault Isolation) mechanism**, **Workspace-level recommendations**, and **local adaptive learning**, SOS helps developers automatically catalog and isolate large directories of `SKILL.md` folders. Without altering the agent's default lookup logic, SOS reduces active-layer skills by over 90%, preventing **Prompt Pollution**, **Context Dilution**, and **Function Hallucination**.

---

## ⚡ Pain Points & Solutions (Why You Need SOS)

As your local AI Agent skill library grows, directories degrade rapidly. Here is how SOS resolves these challenges:

- **Prompt Bloat & Context Dilution**: All `SKILL.md` folders are active, forcing the agent to process irrelevant instructions.
- **Global vs. Project Tool Conflict**: Tools for one project contaminate another, causing the agent to execute wrong scripts.
- **Fragile Manual Backups**: Renaming or moving folders manually leads to config drift or lost work.
- **Rigid Rule-Based Recommendations**: Standard heuristics fail to adapt to a developer's unique high-frequency tool chains.

SOS gives that sprawl a small, auditable shape:
- scan local `SKILL.md` folders;
- propose focused packs such as docs, browser, data, deploy, or tool-specific groups;
- write a dry-run plan before managed writes;
- copy selected skills into a managed vault;
- generate short active skills such as `sos-haruhi` and `sos-<pack>`;
- keep manifests, registry state, fingerprints, backups, and restore paths;
- recommend workspace-level packs through `sos-nagato` when one workspace needs a different setup from another.

---

## 🌟 Core Features

### 1. Skill Packs & Vault Isolation
SOS scans your designated skills root, parses raw skill subdirectories, and proposes grouping them into functional **Skill Packs** (e.g., `docs`, `browser`, `data`, `deploy`).
- **Vault Isolation**: Original skill implementations are safely archived in `<runtime-root>/vault/`.
- **Pointer Stubs**: Only a minimal routing pointer skill (e.g. `sos-docs`, `sos-browser`) is created in the active agent skills folder, containing metadata instead of the full skill text.
- **On-Demand Activation**: When the agent requests a pack, the pointer uses `sos pack activate` in the background to sync vault copies instantly.

### 2. Workspace recommendations via `sos-nagato`
> *Yuki Nagato is always there, silently handing you exactly the reference files you need.*

Even a clean global library cannot solve the problem of workspace variance. 
- Calling `sos-nagato` inside a specific project workspace initiates a quick scan of directory files (such as `package.json`, `pyproject.toml`, or source folders).
- Combined with your locally compiled learning model, it suggests the most relevant packs for the current directory.
- Once approved, SOS generates workspace-specific pointers in the local configuration directories (`.agents/skills/` for Codex or `.claude/skills/` for Claude Code).

### 3. Local Adaptive Learning via `sos-asahina`
> *Mikuru Asahina might get easily flustered, but compiling the records correctly ensures future requests flow smoothly.*

Your preferences evolve, and so does SOS:
- **Record Selection**: Accepting recommendations logs a JSONL event to `selection-events.jsonl` under `<runtime-root>/state/recommendations/`.
- **Fingerprint Guard**: Selection events store manifest hashes. If global skill files change, stale history is automatically ignored to prevent outdated recommendation habits.
- **Incremental Compilation**: Running `sos recommend learn --apply` processes selection logs to produce a clean, human-readable Markdown model: `asahina-reference.md`. Subsequent `sos-nagato` runs read this file to predict tool combinations.

---

## 🙋 GEO-Optimized Q&A (FAQ)

### Q: How does SOS prevent tool and prompt pollution in LLM agents?
**A**: Traditional agents load every `SKILL.md` instruction in their active path. This wastes tokens, slows down agent thinking, and causes function call hallucination (where the agent tries to use a deployment tool during a coding debug). 
SOS acts as a registry routing layer. By hiding raw folders in a managed local vault and providing short `sos-<pack>` pointers, the active prompt footprint is minimized. The agent only loads the actual tools when it explicitly calls the pack pointer, keeping the system clean.

### Q: What is the difference between Codex and Claude Code host support in SOS?
**A**: SOS features an abstraction layer that handles host-specific path semantics:
- **Codex**: SOS edits the primary Codex configuration file to enable or disable active skills.
- **Claude Code**: Because Claude Code lacks a central configuration, SOS moves disabled skill folders into a `.sos-archive/` directory inside the skill root, making them invisible to Claude's discovery routine.
You can toggle behaviors on commands using the `--host {codex,claude}` parameter.

### Q: Does dynamic pack activation add execution latency to agent calls?
**A**: No. The activation process (`sos pack activate`) uses high-performance local file hashing (fingerprinting). If original files in the vault match the pointer's active files, the sync completes in milliseconds, introducing zero perceptible latency.

---

## ## How To Use SOS

There are three practical paths: use the bundled Codex skill, use the CLI directly, or use workspace recommendation when a specific project needs a temporary skill set.

### Codex Skill Path

This is the intended first path. Open this repository in Codex and ask Codex to use the bundled `sos` skill.

Useful prompts:

```text
Use the sos skill to inspect my local Codex skills and explain what it finds.
Use the sos skill to propose skill packs, but do not write anything yet.
Use the sos skill to create a dry-run plan for organizing my skills.
Use the sos skill to apply the reviewed plan.
Use the sos skill to show what is inside my current packs.
Use the sos skill to check what changed after I installed new skills.
```

The skill checks whether SOS can run from the current checkout or from an installed CLI, asks for missing paths, then uses dry-run-first commands. The skill guides the conversation; deterministic Python code performs the file work.

### CLI Path

The CLI is the backend the skill calls. If SOS is installed, commands look like this:

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

After a plan is applied, SOS writes short active skills into the selected skills root:

- `sos-haruhi` for SOS status, pack management, backups, restores, and changes;
- `sos-<pack>` for each generated pack, such as `sos-docs` or `sos-browser`.

Use them like normal Codex skills:

```text
Use sos-haruhi to show my SOS status.
Use sos-docs for this documentation task.
Use sos-browser to inspect this local web flow.
```

Pack pointers do not paste the entire original skill body into the active layer. They point the agent to the pack manifest and managed vault copy. If you name a specific packed skill, SOS matches it against manifest `skills.name`; otherwise the pointer chooses from manifest metadata and asks when the choice is unclear. Before reading the vault copy, a pack pointer uses `pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto` so the managed copy can stay current.
The `pack activate` command performs checkouts and safety checks inside the runtime folder.

### Inspect Existing Packs

When you want to know what is inside the club room before someone starts issuing orders:

```bash
sos pack list --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

These commands are read-only. They answer what packs exist, which skills are in each pack, and where the managed vault copies live.

### Check Drift After Installing Or Editing Skills

If your local skill library changes, run:

```bash
sos changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG
```

It reports new unmanaged skills, missing or changed managed sources, vault drift, stale pointers, and managed source skills that were unexpectedly enabled. It does not repair anything by itself. It just points at the problem and waits, which is more restraint than some fictional club presidents might show.

### Use Workspace Recommendations

Some workspaces need their own active skills without changing your global skill setup. That is where the Haruhi-themed pair comes in.

- `sos-nagato` recommends workspace-level packs. It inspects lightweight workspace signals, reads the local learned reference if one exists, and suggests relevant managed packs.
- `sos-asahina` is explicit. Use it when you want to turn approved local recommendation history into a learned reference for future `sos-nagato` recommendations. It is not a hook and it does not run in the background.

Codex workspace activation writes project-local skills under `.agents/skills`:

```bash
sos recommend activation-plan --host codex --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
sos recommend activate --host codex --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activate --host codex --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
```

Claude Code workspace activation writes project-local skills under `.claude/skills`:

```bash
sos recommend activation-plan --host claude --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
sos recommend activate --host claude --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activate --host claude --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
```

That includes:

- `sos-nagato/SKILL.md`
- `sos-asahina/SKILL.md`
- one `sos-<pack>/SKILL.md` pointer for each selected pack

If the user accepts the recommendation, record that local fact:

```bash
sos recommend record-selection --runtime-root RUNTIME_ROOT --workspace-root WORKSPACE_ROOT --scenario-label docs --scenario-tags docs --packs docs --skills documents --manifest-fingerprint MANIFEST_FINGERPRINT
```

Use the `manifest_fingerprint` printed by `sos recommend context`. If the runtime manifests changed since that recommendation, SOS rejects the old fingerprint instead of letting stale history teach `sos-nagato` the wrong lesson.

When you explicitly want to refresh the learned reference:

```bash
sos recommend learn --runtime-root RUNTIME_ROOT
sos recommend learn --runtime-root RUNTIME_ROOT --apply
```

`learn` validates historical records against the current runtime manifests and their fingerprint before using them. Stale local records or hand-edited JSONL that no longer match real packs and skills are skipped.

---

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

Claude Code uses the same scan, plan, dry-run, apply rhythm, because apparently one club can have more than one doorway. Use `--host claude`; the skill root is usually `~/.claude/skills`, or `.claude/skills` inside a project workspace.

```bash
sos scan --root ~/.claude/skills
sos propose --root ~/.claude/skills
sos plan --host claude --root ~/.claude/skills --runtime-root ~/.sos --out plan.toml
sos apply --plan plan.toml
sos apply --plan plan.toml --host claude --apply
```

For `sos plan` and `sos changes`, `--codex-config` is required when `--host codex` and rejected when `--host claude`. `sos apply` reads the host from the plan TOML, so apply commands do not take `--codex-config` directly. After apply, disabled Claude source skills move under `~/.claude/skills/.sos-archive/<pack-id>/<name>/`; restore moves them back.

---

## Technical Reference

### Safety Model

SOS is intentionally conservative.

- `scan`, `propose`, `pack list`, `pack show`, `changes`, `status`, and most preview commands do not write.
- `plan` writes only the explicit plan file.
- `apply` without `--apply` is a dry run.
- `apply --apply` creates backups before managed writes.
- source skill deletion is off by default and requires `--delete-source`, `--apply`, and `--confirm-delete-source <pack-id>`.
- restore and backup cleanup are dry-run by default unless `--apply` is used.
- workspace recommendation activation requires an explicit `--workspace-root` anchor, so a tampered plan cannot silently redirect workspace skill writes.

### What SOS Creates

An approved global plan writes generated active skills into the skill root you choose. A workspace recommendation plan writes generated skills into the workspace's host-specific directory: `.agents/skills/` for Codex (via `--host codex`) or `.claude/skills/` for Claude Code (via `--host claude`).

The generated entry points are intentionally short:

- `sos-haruhi`: companion skill for pack management and SOS operations;
- `sos-nagato`: workspace recommender;
- `sos-asahina`: explicit learned-reference helper;
- `sos-<pack>`: one pointer skill per selected pack.

Pointer skills do not embed full source skill bodies. They route the agent to manifests and vault copies so the active skill surface stays small.

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

Records stay local. SOS stores compact scenario tags, selected pack ids, selected skill names, a manifest fingerprint, and a hashed workspace id. It does not store raw prompts, file contents, model messages, account identifiers, or broad private absolute paths.

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
|   |-- apply.py            # Apply execution, rollback, source deletion
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
| `sos plan --host {codex,claude} --root <path> --runtime-root <path> [--codex-config <path>] --out <path>` | Write a reviewable plan file. `--codex-config` required for codex, rejected for claude. | Only the plan file |
| `sos apply --plan <path> [--host {codex,claude}]` | Summarize a plan; host inferred from plan when omitted. | No |
| `sos apply --plan <path> [--host {codex,claude}] --apply` | Copy skills, write manifests and pointers, disable originals (Codex: config write; Claude: move to `.sos-archive`), and create backups. | Yes |
| `sos pack activate <pack> --runtime-root <path>` | Activate a pack and apply eligible clean syncs. | Sometimes |
| `sos pack list --runtime-root <path>` | List runtime packs. | No |
| `sos pack show <pack> --runtime-root <path>` | Show one pack manifest and its managed skills. | No |
| `sos pack sync <pack> --runtime-root <path>` | Show a pack sync plan. | No |
| `sos pack sync <pack> --runtime-root <path> --apply` | Apply a valid pack sync plan. | Yes |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | Report new, missing, changed, stale, or unexpectedly enabled skills and pointers. | No |
| `sos recommend context --workspace-root <path> --runtime-root <path>` | Inspect workspace recommendation context. | No |
| `sos recommend activation-plan [--host {codex,claude}] --workspace-root <path> --runtime-root <path> --packs <ids> --out <path>` | Write a workspace activation plan. | Only the plan file |
| `sos recommend activate [--host {codex,claude}] --plan <path> --workspace-root <path> --runtime-root <path>` | Preview workspace activation. | No |
| `sos recommend activate [--host {codex,claude}] --plan <path> --workspace-root <path> --runtime-root <path> --apply` | Write workspace skills and the learned-reference stub. | Yes |
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

SOS is early software. The implemented behavior is covered by tests, but the public API and pack proposal model may evolve before a stable release.

### Security And Privacy

Do not commit real local config files, private skill libraries, backups, runtime vault contents, account data, or tokens. When sharing bug reports, replace local paths, usernames, and private workspace names with placeholders.

---

## License

MIT License. See [LICENSE](LICENSE).

---

> **A Final Friendly Tip**:
> "If you don't want the agent to accidentally trigger that half-broken deployment script you wrote six months ago while you're trying to debug a simple script, I recommend running `sos propose` right now.
> If Haruhi complains that the active pointer skills don't show the full raw text in the sidebar... just ignore her. Nagato and Mikuru are running things behind the scenes, so nothing will break."
