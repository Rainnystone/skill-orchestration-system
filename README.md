# Skill Orchestration System

[English](README.md) | [中文](README_CN.md)

Skill Orchestration System (SOS) is a local command-line tool for organizing many
agent skills into auditable, activatable packs.

It is designed for users who keep a large skill library but only want a small,
task-focused set of active entry points. SOS scans skill folders, proposes
semantic packs, writes a reviewable plan, copies selected skills into a managed
vault, generates pointer skills, disables original active skills in Codex
configuration, and creates backups before writes.

## What It Does

- Scans local skill folders that contain `SKILL.md`.
- Proposes built-in packs for Apify, Obsidian, and browser game workflows.
- Writes a plan file before making changes.
- Applies the plan only when `--apply` is explicitly passed.
- Preserves source skills by default.
- Generates active pointer skills such as `sos-apify` and `sos-obsidian`.
- Tracks pack manifests, runtime registry state, backups, restore targets, and
  sync fingerprints.
- Supports dry-run status, backup cleanup, restore, and pack sync flows.

## Safety Model

SOS is intentionally conservative:

- `scan`, `propose`, and `plan` do not modify the active skill root.
- `apply` without `--apply` is a dry run.
- `apply --apply` creates backups before writing.
- Source skill deletion is disabled by default and requires all of:
  `--delete-source`, `--apply`, and `--confirm-delete-source <pack-id>`.
- Plugin cache paths are protected from source deletion.
- Restore and cleanup commands are dry-run by default unless `--apply` is used.

Review the generated plan before running any command that writes files.

## Installation

SOS requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

The install command above installs SOS and its runtime dependencies, including
`tomli-w`. You do not need to install `tomli-w` separately unless you are running
the source tree without installing the package.

After installation, the console script is also available as:

```bash
sos --version
```

## Quick Start

The example below uses placeholders. Replace them with your own skill root,
runtime root, and Codex config path.

```bash
export SKILLS_ROOT="$HOME/.codex/skills"
export RUNTIME_ROOT="$HOME/.sos"
export CODEX_CONFIG="$HOME/.codex/config.toml"
```

Scan active skills:

```bash
sos scan --root "$SKILLS_ROOT" --codex-config "$CODEX_CONFIG"
```

Preview built-in pack proposals:

```bash
sos propose --root "$SKILLS_ROOT"
```

Create an auditable plan:

```bash
sos plan \
  --root "$SKILLS_ROOT" \
  --runtime-root "$RUNTIME_ROOT" \
  --codex-config "$CODEX_CONFIG" \
  --out "$RUNTIME_ROOT/plan.toml"
```

Dry-run the plan:

```bash
sos apply --plan "$RUNTIME_ROOT/plan.toml"
```

Apply the plan:

```bash
sos apply --plan "$RUNTIME_ROOT/plan.toml" --apply
```

Check runtime state:

```bash
sos status --runtime-root "$RUNTIME_ROOT"
```

## CLI Reference

| Command | Purpose | Writes by default |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | List enabled skills under a root. | No |
| `sos propose --root <path>` | Propose built-in packs from scanned skills. | No |
| `sos plan --root <path> --runtime-root <path> --codex-config <path> --out <path>` | Write a reviewable plan file. | Only the plan file |
| `sos apply --plan <path>` | Summarize a plan. | No |
| `sos apply --plan <path> --apply` | Copy skills, write manifests and pointers, disable originals, and create backups. | Yes |
| `sos pack activate <pack> --runtime-root <path>` | Activate a pack and apply eligible clean syncs. | Sometimes |
| `sos pack sync <pack> --runtime-root <path>` | Show a pack sync plan. | No |
| `sos pack sync <pack> --runtime-root <path> --apply` | Apply a valid pack sync plan. | Yes |
| `sos status --runtime-root <path>` | Show runtime registry and backup state. | No |
| `sos backup list --runtime-root <path>` | List backups. | No |
| `sos backup clean --runtime-root <path> --keep <count>` | Preview backup pruning. | No |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | Prune old backups. | Yes |
| `sos restore <backup-id> --runtime-root <path>` | Preview restore targets. | No |
| `sos restore <backup-id> --runtime-root <path> --apply` | Restore recorded config and vault targets. | Yes |

## Runtime Layout

The runtime root is the managed SOS workspace. A typical runtime looks like:

```text
<runtime-root>/
  backups/
  packs/
  state/
  vault/
```

- `vault/` stores copied pack skills.
- `packs/` stores TOML pack manifests.
- `state/` stores registry state.
- `backups/` stores config and vault snapshots created before writes.

## Built-In Pack Proposals

SOS currently recognizes these built-in families:

- `apify`: skills whose names start with `apify-`.
- `obsidian`: skills whose names start with `obsidian-`, plus `json-canvas`.
- `game-design`: Game Studio and browser game workflow skills.

Large families are split into stable semantic subpacks when needed.

## Source Deletion

Source folders are not deleted during normal activation. If you intentionally
want to remove source skills after they have been copied into the SOS vault, run:

```bash
sos apply \
  --plan "$RUNTIME_ROOT/plan.toml" \
  --apply \
  --delete-source \
  --confirm-delete-source <pack-id>
```

Use this only after reviewing the plan and confirming backups exist.

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
```

Run a CLI smoke check:

```bash
python -m sos --version
```

## Project Status

SOS is an early local CLI. The implemented behavior is covered by tests, but the
public API and pack proposal set may evolve before a stable release.

## Contributing

Issues and pull requests are welcome. Please keep changes small, covered by
tests, and aligned with the dry-run-first safety model.

## Security And Privacy

Do not commit real local config files, private skill libraries, backups, or
runtime vault contents. When sharing bug reports, replace local paths, usernames,
tokens, and private workspace names with placeholders.

## License

MIT License. See [LICENSE](LICENSE).
