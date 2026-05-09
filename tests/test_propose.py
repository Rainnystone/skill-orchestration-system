from pathlib import Path

from sos.propose import PackProposal, propose_builtin_packs
from sos.scanner import ScannedSkill, scan_skill_roots


def test_propose_builtin_packs_returns_only_v1_builtin_packs():
    skills = scan_skill_roots([Path("tests/fixtures/skills")])

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == (
        "apify",
        "obsidian",
        "game-design",
    )


def test_proposal_objects_include_pack_id_skill_names_and_reason():
    skills = scan_skill_roots([Path("tests/fixtures/skills")])

    proposals = propose_builtin_packs(skills)

    apify = proposals[0]
    assert apify.pack_id == "apify"
    assert apify.skill_names == ("apify-actor-development",)
    assert "Apify" in apify.reason


def test_frontend_ui_ux_skills_are_not_v1_builtin_pack_proposals(tmp_path: Path):
    frontend_skill = ScannedSkill(
        name="frontend-skill",
        description="Build front-end UI and UX prototypes.",
        folder=tmp_path / "frontend-skill",
        skill_md=tmp_path / "frontend-skill" / "SKILL.md",
    )
    skills = scan_skill_roots([Path("tests/fixtures/skills")]) + (frontend_skill,)

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == (
        "apify",
        "obsidian",
        "game-design",
    )
    assert all("frontend-skill" not in proposal.skill_names for proposal in proposals)


def test_pack_proposal_freezes_skill_names_from_external_mutation():
    skill_names = ["first"]

    proposal = PackProposal(pack_id="demo", skill_names=skill_names, reason="Demo pack.")
    skill_names.append("second")

    assert proposal.skill_names == ("first",)


def test_oversized_builtin_pack_proposals_split_by_skill_family(tmp_path: Path):
    skill_names = (
        tuple(f"apify-actor-{index:02}" for index in range(8))
        + tuple(f"apify-market-{index:02}" for index in range(7))
        + tuple(f"apify-social-{index:02}" for index in range(7))
    )
    skills = tuple(
        ScannedSkill(
            name=name,
            description="Apify tool skill.",
            folder=tmp_path / name,
            skill_md=tmp_path / name / "SKILL.md",
        )
        for name in skill_names
    )

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == (
        "apify-actor",
        "apify-market",
        "apify-social",
    )
    assert tuple(
        name for proposal in proposals for name in proposal.skill_names
    ) == tuple(sorted(skill_names))
    assert all(len(proposal.skill_names) <= 20 for proposal in proposals)
    assert all("More than 20" in proposal.reason for proposal in proposals)
    assert all("skill/tool family" in proposal.reason for proposal in proposals)
    assert "apify-2" not in tuple(proposal.pack_id for proposal in proposals)


def test_propose_uses_description_for_source_tool_family(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="vault-helper",
            description="Manage Obsidian vault workflows.",
            folder=tmp_path / "vault-helper",
            skill_md=tmp_path / "vault-helper" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == ("obsidian",)
    assert proposals[0].skill_names == ("vault-helper",)
    assert "description" in proposals[0].reason.lower()


def test_propose_uses_canvas_description_for_obsidian_family(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="canvas-helper",
            description="Manage Canvas workflows.",
            folder=tmp_path / "canvas-helper",
            skill_md=tmp_path / "canvas-helper" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == ("obsidian",)
    assert proposals[0].skill_names == ("canvas-helper",)


def test_propose_does_not_group_ambiguous_head_terms(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="canvas-game-builder",
            description="Build HTML canvas games.",
            folder=tmp_path / "canvas-game-builder",
            skill_md=tmp_path / "canvas-game-builder" / "SKILL.md",
        ),
        ScannedSkill(
            name="three-report-helper",
            description="Compare three report formats.",
            folder=tmp_path / "three-report-helper",
            skill_md=tmp_path / "three-report-helper" / "SKILL.md",
        ),
        ScannedSkill(
            name="image-renderer",
            description="Render images from prompts.",
            folder=tmp_path / "image-renderer",
            skill_md=tmp_path / "image-renderer" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    assert proposals == ()


def test_source_family_takes_priority_over_functional_terms(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="apify-browser-runner",
            description="Use Apify to automate browser data extraction.",
            folder=tmp_path / "apify-browser-runner",
            skill_md=tmp_path / "apify-browser-runner" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == ("apify",)
    assert proposals[0].skill_names == ("apify-browser-runner",)


def test_game_prefix_skills_remain_game_design_source_family(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="game-balance",
            description="Tune combat encounters.",
            folder=tmp_path / "game-balance",
            skill_md=tmp_path / "game-balance" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == ("game-design",)
    assert proposals[0].skill_names == ("game-balance",)


def test_propose_uses_skill_head_for_conservative_functional_groups(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="docx-editor",
            description="Edit docx documents and reports.",
            folder=tmp_path / "docx-editor",
            skill_md=tmp_path / "docx-editor" / "SKILL.md",
        ),
        ScannedSkill(
            name="markdown-editor",
            description="Edit markdown documentation.",
            folder=tmp_path / "markdown-editor",
            skill_md=tmp_path / "markdown-editor" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    assert tuple(proposal.pack_id for proposal in proposals) == ("docs",)
    assert proposals[0].skill_names == ("docx-editor", "markdown-editor")
    assert "functional" in proposals[0].reason.lower()


def test_propose_covers_documented_functional_groups(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="playwright-browser",
            description="Inspect pages and automate browser workflows.",
            folder=tmp_path / "playwright-browser",
            skill_md=tmp_path / "playwright-browser" / "SKILL.md",
        ),
        ScannedSkill(
            name="render-deploy",
            description="Deploy and host services on Render.",
            folder=tmp_path / "render-deploy",
            skill_md=tmp_path / "render-deploy" / "SKILL.md",
        ),
        ScannedSkill(
            name="csv-transform",
            description="Transform CSV datasets for analytics.",
            folder=tmp_path / "csv-transform",
            skill_md=tmp_path / "csv-transform" / "SKILL.md",
        ),
    )

    proposals = propose_builtin_packs(skills)

    by_pack = {proposal.pack_id: proposal.skill_names for proposal in proposals}
    assert by_pack["browser"] == ("playwright-browser",)
    assert by_pack["deploy"] == ("render-deploy",)
    assert by_pack["data"] == ("csv-transform",)


def test_propose_skips_skills_that_match_multiple_functional_groups(tmp_path: Path):
    skills = (
        ScannedSkill(
            name="browser-docs-helper",
            description="Capture browser screenshots for documentation.",
            folder=tmp_path / "browser-docs-helper",
            skill_md=tmp_path / "browser-docs-helper" / "SKILL.md",
        ),
    )

    assert propose_builtin_packs(skills) == ()
