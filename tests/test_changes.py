from __future__ import annotations

from pathlib import Path

from sos.changes import detect_changes
from sos.fingerprint import fingerprint_dir
from sos.manifest import save_pack_manifest, save_registry
from sos.models import PackManifest, Registry, SkillEntry
from sos.paths import RuntimePaths


def _write_skill(folder: Path, name: str, body: str = "body") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name}\n---\n{body}\n", encoding="utf-8"
    )
    return folder


def test_changes_does_not_flag_archived_skill_as_missing(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    archive_folder = skill_root / ".sos-archive" / "demo" / "demo-skill"
    _write_skill(archive_folder, "demo-skill")

    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    runtime_paths.vault.mkdir(parents=True)
    runtime_paths.state.mkdir(parents=True)
    runtime_paths.packs.mkdir(parents=True)
    vault_folder = runtime_paths.vault / "demo" / "demo-skill"
    _write_skill(vault_folder, "demo-skill")
    fingerprint = fingerprint_dir(archive_folder)

    skill = SkillEntry(
        name="demo-skill",
        source_path=skill_root / "demo-skill",
        vault_path=vault_folder,
        archived_source_path=archive_folder,
        last_source_fingerprint=fingerprint,
        last_vault_fingerprint=fingerprint_dir(vault_folder),
    )
    manifest = PackManifest(
        id="demo",
        display_name="Demo",
        pointer_skill="sos-demo",
        host="claude",
        skills=(skill,),
        vault_root=runtime_paths.vault / "demo",
    )
    save_pack_manifest(runtime_paths.packs / "demo.toml", manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(packs=(manifest,), active_pointers=("sos-haruhi", "sos-demo")),
    )

    report = detect_changes(skill_root, runtime_paths, None)
    assert not any(s.name == "demo-skill" for s in report.source_missing)


def test_changes_flags_unarchived_skill_as_managed_source_enabled(tmp_path):
    """User manually moved a folder out of .sos-archive — flag it."""
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    archive_folder = skill_root / ".sos-archive" / "demo" / "demo-skill"
    _write_skill(archive_folder, "demo-skill")
    # Simulate user un-archiving by also placing it at the original location.
    _write_skill(skill_root / "demo-skill", "demo-skill")

    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    runtime_paths.vault.mkdir(parents=True)
    runtime_paths.state.mkdir(parents=True)
    runtime_paths.packs.mkdir(parents=True)
    vault_folder = runtime_paths.vault / "demo" / "demo-skill"
    _write_skill(vault_folder, "demo-skill")

    skill = SkillEntry(
        name="demo-skill",
        source_path=skill_root / "demo-skill",
        vault_path=vault_folder,
        archived_source_path=archive_folder,
        last_source_fingerprint=fingerprint_dir(archive_folder),
        last_vault_fingerprint=fingerprint_dir(vault_folder),
    )
    manifest = PackManifest(
        id="demo",
        display_name="Demo",
        pointer_skill="sos-demo",
        host="claude",
        skills=(skill,),
        vault_root=runtime_paths.vault / "demo",
    )
    save_pack_manifest(runtime_paths.packs / "demo.toml", manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(packs=(manifest,), active_pointers=("sos-haruhi", "sos-demo")),
    )

    report = detect_changes(skill_root, runtime_paths, None)
    assert any(s.name == "demo-skill" for s in report.managed_source_enabled)


def test_changes_reports_missing_archive_as_source_missing(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()

    runtime_paths = RuntimePaths.from_root(tmp_path / "runtime")
    runtime_paths.vault.mkdir(parents=True)
    runtime_paths.state.mkdir(parents=True)
    runtime_paths.packs.mkdir(parents=True)
    vault_folder = runtime_paths.vault / "demo" / "demo-skill"
    _write_skill(vault_folder, "demo-skill")

    skill = SkillEntry(
        name="demo-skill",
        source_path=skill_root / "demo-skill",
        vault_path=vault_folder,
        archived_source_path=skill_root / ".sos-archive" / "demo" / "demo-skill",
        last_vault_fingerprint=fingerprint_dir(vault_folder),
    )
    manifest = PackManifest(
        id="demo",
        display_name="Demo",
        pointer_skill="sos-demo",
        host="claude",
        skills=(skill,),
        vault_root=runtime_paths.vault / "demo",
    )
    save_pack_manifest(runtime_paths.packs / "demo.toml", manifest)
    save_registry(
        runtime_paths.state / "registry.toml",
        Registry(packs=(manifest,), active_pointers=("sos-haruhi", "sos-demo")),
    )

    report = detect_changes(skill_root, runtime_paths, None)
    assert any(s.name == "demo-skill" for s in report.source_missing)
