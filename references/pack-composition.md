# Pack Composition

SOS pack composition uses Agent Skill head metadata: `name` and `description`.
The CLI emits reviewable proposals; it does not let opaque model output write
pack membership.

Implemented priority:

1. Source or tool family: Apify, Obsidian/Canvas, and Game Design.
2. Function or domain: Docs, Browser, Deploy, and Data.
3. Ambiguous skills: no proposal.

Grouping uses skill-head terms only. The full `SKILL.md` body, scripts,
references, and assets are not classification inputs.

Proposal reasons name the signal used, such as source/tool family or functional
terms in `name` or `description`.

## Pack Head

Each pack also needs a short pack head in manifest `description`. This is the
pack-level equivalent of an Agent Skill `description`: it is for agent routing,
so it should describe what the user may ask for and what the pack can do.

The pack head is separate from the proposal reason:

- `reason` explains why SOS grouped these skills together.
- `description` explains when an agent should choose the generated `sos-<pack>`
  pointer skill.

Pack heads may be written by a human or drafted by an agent as reviewable semantic
synthesis over selected skill heads. This reviewable semantic synthesis
compresses the included skills' `name` and `description` fields into one
natural, concise sentence with user-facing terms such as "web scraping",
"Feishu", "UI/UX", "PowerPoint", or "deployment".

The CLI must not call a model, infer hidden intent from opaque model output, or
silently rewrite a pack head after sync. If an agent or LLM drafts or improves a
pack head, that text must appear in a reviewable plan before SOS writes it.
