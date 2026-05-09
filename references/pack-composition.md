# Pack Composition

SOS pack composition should stay deterministic, reviewable, and aligned with
Agent Skill progressive disclosure. A pack proposal should explain why skills
belong together without reading more skill content than needed.

## Skill Head First

For composition, the skill head is the YAML frontmatter at the top of
`SKILL.md`. SOS should use these fields first:

- `name`: the canonical skill identifier.
- `description`: the short explanation of what the skill does and when an
  agent should use it.

This matches the Agent Skill discovery model: agents can see skill metadata
before loading the full skill body. Therefore, basic pack grouping should use
`name` and `description`, not the full Markdown body, scripts, references, or
assets.

If frontmatter is missing or invalid, the folder name is a fallback for the
skill name and the description is empty. Empty or vague metadata should make the
proposal more conservative, not more speculative.

## Grouping Priority

Pack grouping should follow this order.

1. Source or tool family.
   If skill heads clearly share the same product, vendor, tool, or namespace,
   group by that family first. Examples include `apify-*`, `lark-*`,
   `speckit-*`, `obsidian-*`, or descriptions that clearly name the same tool.

2. Function or domain.
   If names do not point to one shared source, group by the job described in the
   skill head. Examples include docs, browser, game, deploy, data, PDF,
   spreadsheet, presentation, and review workflows.

3. Scenario or workflow.
   If the skill heads describe a repeated end-to-end workflow, a scenario pack
   is acceptable even when the skills come from different sources. This should
   be used only when the relationship is obvious from names and descriptions.

4. No automatic pack.
   If the relationship is weak, ambiguous, or based on details that require
   reading the full skill body, do not automatically pack the skills. Surface
   them for human review instead.

## Functional Signals

Functional grouping should be inferred from the skill head only.

- Docs: names or descriptions mention documents, markdown, docx, reports,
  writing, editing, or publishing.
- Browser: names or descriptions mention browsers, Playwright, screenshots,
  page inspection, web interaction, or web automation.
- Game: names or descriptions mention games, gameplay, sprites, Phaser, Three,
  WebGL, playtesting, or game UI.
- Deploy: names or descriptions mention deployment, hosting, releases, Render,
  Vercel, Docker, infrastructure, or publish flows.
- Data: names or descriptions mention CSV, JSON, SQL, analytics, extraction,
  transforms, or datasets.

These labels are not hardcoded authority. They are examples of conservative
signals that can produce reviewable proposals.

## Pack Size And Splitting

Small packs are easier to inspect and activate. If one family or function grows
too large, split it by the next stable token in the skill head instead of
reading skill bodies to invent a hidden taxonomy.

For example:

- `apify-*` can split by the next meaningful token after `apify`.
- `game-*` can split by browser game, asset pipeline, playtest, or UI signals
  when those signals are present in names or descriptions.
- Functional packs can split by a clearer sub-function from descriptions, such
  as docs-writing versus docs-conversion.

## Proposal Reasons

Every proposal should carry a human-readable reason. The reason should name the
metadata signal used, such as:

- shared source family in skill names;
- shared tool named in descriptions;
- shared functional terms in descriptions;
- scenario relationship visible from skill heads.

The reason should not claim that SOS analyzed full skill instructions unless the
implementation actually did so and the user explicitly requested that deeper
inspection.

## Pointer Skill Selection

Generated `sos-<pack>` pointer skills should route through the pack manifest and
managed vault copy. When a user asks for a specific skill inside a pack, the
agent should match the requested name against manifest `skills.name` first, then
read that selected vault skill's `SKILL.md`.

If the user does not name a skill, the agent can choose from the manifest using
the skill names and descriptions. If multiple skills fit equally well, ask the
user to choose instead of reading all packed skills up front.
