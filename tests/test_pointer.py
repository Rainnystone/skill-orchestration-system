import tomllib
from pathlib import Path

import pytest

import sos.pointer as pointer
from sos.models import PackManifest, Registry, SkillEntry
from sos.pointer import (
    render_companion_skill,
    render_pack_pointer,
    render_v1_active_skills,
)


def _manifest(tmp_path: Path, pack_id: str, pointer_skill: str) -> PackManifest:
    vault_root = tmp_path / ".sos" / "vault" / pack_id
    return PackManifest(
        id=pack_id,
        display_name=pack_id.replace("-", " ").title(),
        description=f"{pack_id} skill pack.",
        pointer_skill=pointer_skill,
        aliases=(pack_id,),
        vault_root=vault_root,
        skills=(
            SkillEntry(
                name=f"{pack_id}-skill",
                source_path=tmp_path / "source" / f"{pack_id}-skill",
                vault_path=vault_root / f"{pack_id}-skill",
            ),
        ),
    )


def test_render_pack_pointer_is_short_and_mentions_activation_manifest_and_vault_selection(
    tmp_path: Path,
):
    target = tmp_path / "active" / "sos-apify" / "SKILL.md"
    manifest = _manifest(tmp_path, "apify", "sos-apify")
    expected_manifest_path = tmp_path / ".sos" / "packs" / "apify.toml"

    render_pack_pointer(target, manifest)

    rendered = target.read_text(encoding="utf-8")
    assert len(rendered.splitlines()) < 80
    assert "sos pack activate apify --sync=clean-auto" in rendered
    assert str(expected_manifest_path) in rendered
    assert "choose the matching vault skill from the manifest" in rendered


def test_render_companion_skill_mentions_management_commands_and_apply_boundary(
    tmp_path: Path,
):
    target = tmp_path / "active" / "sos-haruhi" / "SKILL.md"

    render_companion_skill(target, tmp_path / ".sos" / "state" / "registry.toml")

    rendered = target.read_text(encoding="utf-8")
    for command in ("scan", "propose", "plan", "apply", "status", "backup", "restore"):
        assert command in rendered
    assert "write commands require `--apply`" in rendered


def test_render_v1_active_skills_writes_haruhi_apify_obsidian_game_design(tmp_path: Path):
    active_root = tmp_path / "active"
    manifests = (
        _manifest(tmp_path, "apify", "sos-apify"),
        _manifest(tmp_path, "obsidian", "sos-obsidian"),
        _manifest(tmp_path, "game-design", "sos-game-design"),
    )
    registry = Registry(packs=manifests)

    render_v1_active_skills(active_root, registry, manifests)

    rendered_skill_files = {
        path.relative_to(active_root)
        for path in active_root.glob("sos-*/SKILL.md")
    }
    assert rendered_skill_files == {
        Path("sos-haruhi/SKILL.md"),
        Path("sos-apify/SKILL.md"),
        Path("sos-obsidian/SKILL.md"),
        Path("sos-game-design/SKILL.md"),
    }


def test_rendered_pointer_does_not_embed_full_original_skill_body(tmp_path: Path):
    target = tmp_path / "active" / "sos-apify" / "SKILL.md"
    manifest = _manifest(tmp_path, "apify", "sos-apify")
    skill_md = manifest.skills[0].vault_path / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("FULL BODY SENTINEL\n", encoding="utf-8")

    render_pack_pointer(target, manifest)

    rendered = target.read_text(encoding="utf-8")
    assert "FULL BODY SENTINEL" not in rendered


def test_render_v1_active_skills_rejects_registry_pack_missing_from_manifests(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    apify = _manifest(tmp_path, "apify", "sos-apify")
    stale = _manifest(tmp_path, "stale", "sos-stale")
    registry = Registry(packs=(apify, stale))

    with pytest.raises(ValueError, match="missing manifests.*stale"):
        render_v1_active_skills(active_root, registry, (apify,))

    assert not (active_root / "sos-stale" / "SKILL.md").exists()


def test_render_v1_active_skills_rejects_unsafe_pointer_skill_path(tmp_path: Path):
    active_root = tmp_path / "active"
    unsafe = _manifest(tmp_path, "apify", "../outside")
    registry = Registry(packs=(unsafe,))

    with pytest.raises(ValueError, match="unsafe pointer skill"):
        render_v1_active_skills(active_root, registry, (unsafe,))

    assert not (tmp_path / "outside" / "SKILL.md").exists()


def test_render_companion_skill_rejects_unresolved_template_placeholders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    template_root = tmp_path / "templates"
    template_root.mkdir()
    template_root.joinpath("companion-skill.md.tmpl").write_text(
        "{{registry_path}}\n{{missing_placeholder}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pointer, "_TEMPLATE_ROOT", template_root)

    with pytest.raises(ValueError, match="unresolved template placeholders.*missing_placeholder"):
        render_companion_skill(
            tmp_path / "active" / "sos-haruhi" / "SKILL.md",
            tmp_path / ".sos" / "state" / "registry.toml",
        )


def test_package_templates_match_repo_templates():
    repo_root = Path(__file__).resolve().parents[1]
    package_templates = repo_root / "src" / "sos" / "templates"
    repo_templates = repo_root / "templates"

    for name in ("pointer-skill.md.tmpl", "companion-skill.md.tmpl"):
        assert package_templates.joinpath(name).read_text(encoding="utf-8") == (
            repo_templates / name
        ).read_text(encoding="utf-8")


def test_pyproject_packages_sos_template_resources():
    repo_root = Path(__file__).resolve().parents[1]

    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["setuptools"]["package-data"]["sos"] == ["templates/*.tmpl"]
