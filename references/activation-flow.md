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

## Workspace Recommendation Activation

SOS also supports a workspace-only recommendation path. This flow is for
activating already-managed packs inside one workspace without changing the
global skill root.

1. `sos recommend context --workspace-root <workspace> --runtime-root <.sos>`
   inspects workspace signals, lists available runtime packs, reports whether a
   learned reference is present, and prints recommendations without writing.
2. `sos recommend activation-plan --workspace-root <workspace> --runtime-root <.sos> --packs <ids> --out <workspace-plan.toml>`
   writes an auditable workspace activation plan only.
3. `sos recommend activate --plan <workspace-plan.toml> --workspace-root <workspace> --runtime-root <.sos>`
   previews the workspace activation plan without writing.
4. `sos recommend activate --plan <workspace-plan.toml> --workspace-root <workspace> --runtime-root <.sos> --apply`
   writes workspace-local `.agents/skills/sos-nagato/SKILL.md`,
   `.agents/skills/sos-asahina/SKILL.md`, one `.agents/skills/sos-<pack>/SKILL.md`
   for each selected pack, and the learned-reference stub at
   `state/recommendations/asahina-reference.md`.
5. `sos recommend record-selection --runtime-root <.sos> --workspace-root <workspace> ...`
   appends accepted selection records to
   `state/recommendations/selection-events.jsonl`.
6. `sos recommend learn --runtime-root <.sos>` previews the learned reference,
   and `sos recommend learn --runtime-root <.sos> --apply` writes it to
   `state/recommendations/asahina-reference.md`.

`sos-nagato` is the workspace recommender. It reads the workspace and the local
learned reference, then suggests relevant packs. `sos-asahina` does not do
implicit recommendation work; it is the explicit organizer for approved
recommendation results.

The recommendation flow is local and reviewable. It does not write global
skills, does not use hooks, and does not persist raw prompts, file contents,
model messages, account identifiers, or broad private absolute paths. Accepted
selection records store only a hashed workspace identifier. Recommendation
command output redacts local absolute paths with placeholders such as
`WORKSPACE_ROOT`, `RUNTIME_ROOT`, and `WORKSPACE_PLAN`. Durable scenario labels
are derived from scenario tags rather than free-form prompt text.
