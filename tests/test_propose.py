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
