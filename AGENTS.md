# Agent Instructions

## Project Overview

Skill Orchestration System (SOS) is a local Python CLI for organizing agent
skills into auditable, activatable packs. It scans skill folders, proposes
functional packs, writes reviewable plans, applies migrations only with explicit
confirmation, generates `sos-*` pointer skills, and creates backups before
writes.

This is the public repository. Keep public files free of personal paths, private
workspace details, tokens, account data, and local planning logs.

## Public vs Local Files

Commit public product files:

- `README.md`
- `README_CN.md`
- `LICENSE`
- `pyproject.toml`
- `.github/`
- `src/`
- `tests/`
- `templates/`
- `references/`
- `AGENTS.md`

Keep local workflow files uncommitted. They are intentionally ignored:

- `task_plan.md`
- `progress.md`
- `findings.md`
- `coding-agent-guide.md`
- `documentation-governance.md`
- `docs/`
- `archive/`

Use those ignored files for NHK, planning-with-files, superpowers specs/plans,
and workstream archives. Before any commit, verify they are still ignored.

## Development Rules

- Prefer small, direct, testable changes.
- Keep CLI behavior deterministic at write boundaries.
- Do not replace explicit confirmation with heuristics.
- Preserve the dry-run-first safety model.
- Do not hardcode local absolute paths.
- Do not commit generated runtime state such as `.sos/`, backups, vaults,
  `.venv/`, caches, or `*.egg-info`.
- If a change touches write behavior, backup/restore behavior, source deletion,
  config writes, or pack sync, add or update tests first.

## Commands

Install for development:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
```

Smoke-check the CLI:

```bash
python -m sos --version
```

## Git Hygiene

Before committing:

```bash
git status --short --ignored
git diff --check
python -m pytest
```

Public commits should not include private planning files, local absolute paths,
or generated artifacts. If a sensitive file was accidentally tracked, stop and
remove it from the index before pushing.
