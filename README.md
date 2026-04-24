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
- Proposes functional pack candidates from the scanned skills.
- Writes a plan file before making changes.
- Applies the plan only when `--apply` is explicitly passed.
- Preserves source skills by default.
- Generates active pointer skills such as `sos-<pack>`.
- Tracks pack manifests, runtime registry state, backups, restore targets, and
  sync fingerprints.
- Supports dry-run status, backup cleanup, restore, and pack sync flows.

## Repository Structure

```text
.
|-- .github/workflows/     # CI workflow
|-- references/            # Public behavior and safety references
|-- src/sos/               # CLI and library implementation
|   |-- cli.py             # Command-line entry point
|   |-- planner.py         # Auditable write-plan generation
|   |-- apply.py           # Plan execution and rollback-aware writes
|   |-- sync.py            # Pack activation and clean sync behavior
|   |-- backups.py         # Backup, restore, and retention helpers
|   `-- templates/         # Packaged pointer skill templates
|-- templates/             # Source copies of generated-skill templates
|-- tests/                 # Unit tests and CLI smoke tests
|-- README.md              # English documentation
|-- README_CN.md           # Chinese documentation
|-- pyproject.toml         # Python package metadata
`-- LICENSE
```

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

Preview pack candidates:

```bash
sos propose --root "$SKILLS_ROOT"
```

The proposal step is only a starting point. Review the generated plan and keep,
adjust, or reject pack boundaries before applying changes to a real skill root.

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

After a successful apply, SOS writes generated active skills into the scanned
skill root. The generated entry points are described in the next section.

Check runtime state:

```bash
sos status --runtime-root "$RUNTIME_ROOT"
```

## CLI Reference

| Command | Purpose | Writes by default |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | List enabled skills under a root. | No |
| `sos propose --root <path>` | Propose pack candidates from scanned skills. | No |
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

## Generated Skills

SOS does not commit generated active skill folders to this repository. They are
created in your selected active skill root when an apply plan is executed with
`--apply`.

The generated set includes:

- `sos-haruhi`: the companion entry for pack management, status, backup, and
  restore workflows.
- `sos-<pack>`: one pointer skill per active pack, generated from each pack
  manifest.

Generated pointer skills stay intentionally short. They point the agent to the
pack manifest and vault copy instead of embedding the full original `SKILL.md`
content.

## Pack Proposal Model

SOS treats pack proposals as reviewable candidates, not final authority. A pack
should represent a real workflow boundary, and the generated plan should be
reviewed before any write command runs.

The current proposal engine is intentionally conservative. Future versions may
add more proposal rules, custom manifests, or interactive selection flows.

## Compatibility

SOS is currently Codex-first. Its tested write path can update Codex skill
configuration after creating backups and only when `--apply` is used.

Claude Code compatibility is structural in the current release: generated skills
are ordinary `SKILL.md` folders, and pack metadata is stored in plain TOML
manifests. SOS does not yet provide a Claude Code-specific installer, settings
writer, or integration test suite. Paths that look Claude-specific are guarded
against broad source deletion.

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
