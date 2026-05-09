# SOS Safety Model

SOS is dry-run-first and confirmation-first. Use read-only commands whenever possible, and treat writes as managed CLI operations rather than manual file edits.

## Before Writes

Before applying a plan, activating a pack with sync, restoring a backup, cleaning up generated output, or deleting source files, confirm the exact target root, runtime root, config path, and command mode with the human.

Do not edit Codex config, SOS vaults, manifests, registry files, backups, generated pointer skills, or plan outputs by hand. If those artifacts need to change, use the SOS CLI so validation, backups, and manifests stay consistent.

## Source Deletion

Source deletion must remain opt-in and explicit. Do not suggest or perform source deletion as a cleanup shortcut. Explain what will be deleted and wait for direct human approval before any destructive operation.

## Backups And Restore

Backups protect managed writes, but they are not a reason to skip review. For restore, start with the dry-run form, inspect what would change, then ask for approval before adding `--apply`.

## Documentation

Keep public onboarding docs aligned with the safety model. When install, usage, write-boundary, backup, restore, or activation behavior changes, update both `README.md` and `README_CN.md` in the same change.
