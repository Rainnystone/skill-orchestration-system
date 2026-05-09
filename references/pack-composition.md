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
