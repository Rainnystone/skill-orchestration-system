# Claude Code Notes

SOS supports Claude Code as a host alongside Codex. Use `--host claude` on write
commands when operating against `~/.claude/skills` or a project-level
`.claude/skills` directory.

## Skill Roots

The doctor reports `claude_skill_root` when it finds `~/.claude/skills` or
`<cwd>/.claude/skills`. Use the reported path as `--root`. If both exist, ask
the human which to operate on; do not assume.

## Disable Semantic

Codex disables a skill by writing `enabled = false` in its config TOML. Claude
has no such registry. SOS implements the equivalent semantic as a file system
move:

- before apply: `<skill-root>/<name>/SKILL.md` — Claude can see it
- after apply: `<skill-root>/.sos-archive/<pack-id>/<name>/SKILL.md` — Claude does not

Claude Code skips dot-prefixed subdirectories during skill discovery, so the
archive is invisible to the active skill surface. Restore moves the folder back
to its original location.

## Repo-Local Invocation

Doctor mode detection (advisory / repo-local / installed-cli) is unchanged from
the Codex flow. Run the doctor first; choose the invocation it reports.

## Write Boundary

Treat `.sos-archive/` as managed state. Do not edit, move, or `rm` its contents
by hand. Use `sos restore <backup-id> --runtime-root <.sos> --apply` to bring
archived skills back; use `sos apply --plan <plan.toml> --apply --delete-source
--confirm-delete-source <pack-id>` to remove the archive entries permanently.

## README Alignment

When user-facing install, usage, or workflow entry points change, update both
`README.md` and `README_CN.md` together. The CLI reference table includes a
`--host` column; keep examples for both hosts in sync.
