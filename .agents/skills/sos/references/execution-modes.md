# SOS Execution Modes

SOS supports three operating modes from this skill.

## Advisory Mode

Use advisory mode when no runnable SOS backend is available. In this mode, explain what can be inspected, what cannot be verified, and the smallest missing prerequisite. Do not claim that SOS commands have run.

## Repo-Local Mode

Use repo-local mode when the `skill-orchestration-system` source tree is available but `sos` is not installed globally. The doctor detects this by finding `pyproject.toml`, `src/sos/`, and the project name.

In repo-local mode, invoke SOS with Python and a source-tree import path instead of requiring a global install. Start with read-only commands such as version, scan, propose, plan, dry-run apply, status, or backup list.

## Installed-CLI Mode

Use installed-CLI mode only when the `sos` executable is already available. This is a convenience path, not the first-run assumption.

If both repo-local and installed-CLI are available, prefer installed-CLI for simple commands and repo-local for development work inside the source checkout.
