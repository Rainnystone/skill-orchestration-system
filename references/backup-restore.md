# Backup And Restore

SOS creates backups during apply and exposes backup management commands.

Implemented backup commands:

- `sos backup list --runtime-root <.sos>`
- `sos backup clean --runtime-root <.sos> --keep <count>`
- `sos backup clean --runtime-root <.sos> --keep <count> --apply`
- `sos restore <backup-id> --runtime-root <.sos>`
- `sos restore <backup-id> --runtime-root <.sos> --apply`

Current behavior:

- `sos apply --plan <plan.toml> --apply` backs up Codex config and the SOS vault
  before writing.
- Backup metadata records enough path information for the CLI restore path after
  apply annotates metadata.
- `sos backup list` reports backup ids and snapshot paths.
- `sos backup clean` without `--apply` reports retained backups without deleting.
- `sos backup clean --apply` prunes old backups according to `--keep`.
- `sos restore` without `--apply` reports restore targets without writing.
- `sos restore --apply` restores the recorded config and vault targets.

Restore requires valid backup metadata. Unsafe backup ids are rejected before
reading outside the runtime backup directory.
