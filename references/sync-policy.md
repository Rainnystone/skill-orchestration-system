# Sync Policy

Generated manifests use `sync_policy = "clean-auto"`.

Implemented commands:

- `sos pack activate <pack> --runtime-root <.sos> --sync clean-auto`
- `sos pack sync <pack> --runtime-root <.sos>`
- `sos pack sync <pack> --runtime-root <.sos> --apply`

Current behavior:

- `sos pack activate` reads `<runtime-root>/packs/<pack>.toml`.
- `clean-auto` activation can apply a clean sync when the source and vault state
  are eligible.
- `sos pack sync` without `--apply` reports the sync plan and does not write.
- `sos pack sync --apply` copies source skill folders to the vault when the sync
  plan is valid and updates manifest sync fingerprints.
- Conflicts and stale-source states are reported instead of being hidden.

This reference only describes the implemented `clean-auto` path. Additional sync
policies are not part of the current tested behavior.
