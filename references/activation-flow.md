# Activation Flow

The implemented SOS activation flow is deterministic and human-confirmed at the
write boundary.

1. `sos scan --root <skills>` lists active skill folders containing `SKILL.md`.
2. `sos scan --root <skills> --codex-config <config.toml>` excludes disabled
   skill paths from `[skills].config`.
3. `sos propose --root <skills>` proposes built-in packs for matching Apify,
   Obsidian, and Game Design skill families.
4. `sos plan --root <skills> --runtime-root <.sos> --codex-config <config.toml> --out <plan.toml>`
   writes an auditable plan file only.
5. `sos apply --plan <plan.toml>` prints the plan summary without writes.
6. `sos apply --plan <plan.toml> --apply` copies skills to the vault, writes
   manifests and registry, writes `sos-*` pointer skills, disables original
   skill paths in Codex config, and creates backups.
7. `sos status --runtime-root <.sos>` reports registry and backup state.

Deletion is separate from activation. Source folders are preserved by default.
Source deletion requires `sos apply --plan <plan.toml> --apply --delete-source
--confirm-delete-source <pack-id>` and is validated against the plan.
