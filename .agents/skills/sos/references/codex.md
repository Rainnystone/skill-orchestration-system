# Codex Notes

This SOS skill is Codex-first. It assumes the user may have the repository checkout available without a global `sos` executable.

## Skill Roots

Use `scripts/sos_doctor.py` to identify whether the current context looks like advisory mode, repo-local mode, or installed-CLI mode. Ask the human for missing paths instead of guessing private local defaults.

## Config Writes

Do not write Codex configuration by hand. Use SOS commands for managed config updates, and prefer dry-run or plan output before any apply operation.

## Repo-Local Invocation

When working inside the source checkout, invoke SOS through Python with the repository source tree on the import path reported by `scripts/sos_doctor.py`. Keep command examples specific to the selected workflow rather than pasting a full CLI reference.

## README Timing

README rewrite is deferred. Ask the human for the README style before rewriting public README files.
