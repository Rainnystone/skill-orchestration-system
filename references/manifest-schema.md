# Manifest Schema

Pack manifests are TOML files written by `sos plan` metadata and materialized by
`sos apply --apply` under `<runtime-root>/packs/<pack-id>.toml`.

Implemented pack-level fields:

- `id`: stable pack id, such as `apify`, `obsidian`, or `game-design`.
- `display_name`: human-readable pack name.
- `aliases`: alternate names mapped in the runtime registry.
- `description`: short pack description used by generated pointer text.
- `pointer_skill`: generated active pointer skill name, such as `sos-apify`.
- `sync_policy`: currently planned as `clean-auto` by generated manifests.
- `paths.vault_root`: pack vault directory, normally `<runtime-root>/vault/<pack-id>`.
- `triggers`: trigger metadata carried by the manifest when present.

Implemented skill entry fields:

- `skills.name`: source skill name.
- `skills.source_path`: original active skill folder copied from the scanned root.
- `skills.vault_path`: copied skill folder under the SOS vault.
- `skills.origin`: source environment label.
- `skills.enabled_before_apply`: whether the source skill was enabled before apply.
- `skills.last_source_fingerprint`: source directory fingerprint after planning.
- `skills.last_vault_fingerprint`: vault directory fingerprint after sync.
- `skills.last_synced_at`: timestamp recorded by sync when available.

Related commands:

- `sos plan` writes the auditable plan that contains manifest metadata.
- `sos apply --apply` writes pack manifests, registry, vault copies, pointers, and config disables.
- `sos status --runtime-root <.sos>` summarizes written runtime state.
