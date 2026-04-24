# Codex Config Safety

SOS uses Codex config only at explicit command boundaries.

Implemented read behavior:

- `sos scan --root <skills> --codex-config <config.toml>` reads disabled entries
  from `[skills].config` and excludes matching skill paths.
- Missing config files are treated as having no disabled paths for scan.

Implemented write behavior:

- `sos plan` does not modify Codex config.
- `sos apply --plan <plan.toml>` does not modify Codex config.
- `sos apply --plan <plan.toml> --apply` disables original skill `SKILL.md`
  paths in `[skills].config` and creates a config backup first.
- Config writes are atomic and rollback-aware through the apply path.

Fixture shape:

```toml
model = "gpt-5.5"

[skills]
config = []
```

The disabled entry shape written by apply is:

```toml
[[skills.config]]
path = "/absolute/path/to/SKILL.md"
enabled = false
```

Related commands:

- `sos scan`
- `sos plan`
- `sos apply`
- `sos backup list`
- `sos backup clean`
- `sos restore`
