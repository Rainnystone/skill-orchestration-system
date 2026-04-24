from pathlib import Path
import shutil

import pytest

from sos.skill_fs import copy_skill_folder, replace_skill_folder_atomic, validate_skill_folder


def test_validate_skill_folder_requires_skill_md(tmp_path: Path):
    skill = tmp_path / "missing-skill-md"
    skill.mkdir()

    with pytest.raises(ValueError) as error:
        validate_skill_folder(skill)

    assert "Missing SKILL.md" in str(error.value)


def test_copy_skill_folder_preserves_scripts_assets_data_and_references(tmp_path: Path):
    source = tmp_path / "source-skill"
    target = tmp_path / "target-skill"
    files = {
        "SKILL.md": "# Demo\n",
        "scripts/tool.py": "print('tool')\n",
        "assets/icon.txt": "icon\n",
        "data/example.json": '{"ok": true}\n',
        "references/guide.md": "# Guide\n",
    }
    for relative_path, text in files.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    copy_skill_folder(source, target)

    for relative_path, text in files.items():
        assert (target / relative_path).read_text(encoding="utf-8") == text


def test_replace_skill_folder_uses_temp_dir_and_keeps_old_target_on_copy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source-skill"
    source.mkdir()
    (source / "SKILL.md").write_text("# New\n", encoding="utf-8")
    target = tmp_path / "target-skill"
    target.mkdir()
    (target / "SKILL.md").write_text("# Old\n", encoding="utf-8")
    copytree_destinations: list[Path] = []

    def fail_copytree(src: Path, dst: Path, *args, **kwargs):
        destination = Path(dst)
        copytree_destinations.append(destination)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "partial.txt").write_text("partial\n", encoding="utf-8")
        raise RuntimeError("copy failed")

    monkeypatch.setattr(shutil, "copytree", fail_copytree)

    with pytest.raises(RuntimeError, match="copy failed"):
        replace_skill_folder_atomic(source, target)

    assert (target / "SKILL.md").read_text(encoding="utf-8") == "# Old\n"
    assert len(copytree_destinations) == 1
    assert copytree_destinations[0].parent == target.parent
    assert copytree_destinations[0] != target
