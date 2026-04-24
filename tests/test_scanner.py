from pathlib import Path

from sos.scanner import scan_skill_roots


def test_scan_skill_roots_reads_frontmatter_and_skill_md_path():
    skills = scan_skill_roots([Path("tests/fixtures/skills")])

    by_name = {skill.name: skill for skill in skills}
    assert by_name["apify-actor-development"].description == "Develop and debug Apify Actors."
    assert by_name["obsidian-cli"].description == "Manage Obsidian vaults with the Obsidian CLI."
    assert by_name["game-studio"].description == "Route browser game design and implementation work."
    assert by_name["apify-actor-development"].folder == Path(
        "tests/fixtures/skills/apify-actor-development"
    )
    assert by_name["apify-actor-development"].skill_md == Path(
        "tests/fixtures/skills/apify-actor-development/SKILL.md"
    )


def test_scan_skill_roots_excludes_disabled_skill_md_paths():
    disabled = Path("tests/fixtures/skills/obsidian-cli/SKILL.md")

    skills = scan_skill_roots([Path("tests/fixtures/skills")], disabled_paths=(disabled,))

    assert tuple(skill.name for skill in skills) == (
        "apify-actor-development",
        "game-studio",
    )

