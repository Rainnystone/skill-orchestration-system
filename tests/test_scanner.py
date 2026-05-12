from pathlib import Path

import pytest

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


def test_scan_frontmatter_does_not_use_full_file_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    root = tmp_path / "skills"
    skill_dir = root / "large-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: large-skill\n"
        "description: Frontmatter only.\n"
        "---\n"
        "# Large Skill\n"
        "Body content that should not be read eagerly.\n",
        encoding="utf-8",
    )

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args, **kwargs) -> str:
        if self == skill_md:
            raise AssertionError("scan should not read the full SKILL.md body")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    skills = scan_skill_roots((root,))

    assert len(skills) == 1
    assert skills[0].name == "large-skill"
    assert skills[0].description == "Frontmatter only."


def test_scanner_excludes_sos_archive_subtree(tmp_path):
    from sos.scanner import scan_skill_roots

    root = tmp_path / "skills"
    root.mkdir()

    live_skill = root / "live"
    live_skill.mkdir()
    (live_skill / "SKILL.md").write_text(
        "---\nname: live\ndescription: live\n---\n", encoding="utf-8"
    )

    archived = root / ".sos-archive" / "pack" / "archived"
    archived.mkdir(parents=True)
    (archived / "SKILL.md").write_text(
        "---\nname: archived\ndescription: archived\n---\n", encoding="utf-8"
    )

    found = scan_skill_roots((root,))
    names = {skill.name for skill in found}
    assert "live" in names
    assert "archived" not in names
