from pathlib import Path

import pytest

from sos.active_namespace import (
    COMPANION_POINTER_SKILL,
    validate_active_skill_namespace,
)


def test_active_namespace_rejects_source_name_colliding_with_pointer_name(
    tmp_path: Path,
):
    with pytest.raises(ValueError, match="active skill namespace collision"):
        validate_active_skill_namespace(
            tmp_path / "active",
            source_skill_names=("sos-demo",),
            pointer_skill_names=("sos-demo",),
            managed_pointer_names=(),
        )


def test_active_namespace_rejects_pointer_name_colliding_with_companion(
    tmp_path: Path,
):
    with pytest.raises(ValueError, match="active skill namespace collision"):
        validate_active_skill_namespace(
            tmp_path / "active",
            source_skill_names=("alpha",),
            pointer_skill_names=(COMPANION_POINTER_SKILL,),
            managed_pointer_names=(),
        )


def test_active_namespace_rejects_unicode_casefold_collision(tmp_path: Path):
    with pytest.raises(ValueError, match="active skill namespace collision"):
        validate_active_skill_namespace(
            tmp_path / "active",
            source_skill_names=("de\u0301mo",),
            pointer_skill_names=("démo",),
            managed_pointer_names=(),
        )


def test_active_namespace_rejects_existing_unmanaged_pointer_folder(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    (active_root / "sos-demo").mkdir(parents=True)

    with pytest.raises(ValueError, match="active skill namespace collision"):
        validate_active_skill_namespace(
            active_root,
            source_skill_names=("alpha",),
            pointer_skill_names=("sos-demo",),
            managed_pointer_names=(),
        )


def test_active_namespace_rejects_case_mismatched_managed_pointer_folder(
    tmp_path: Path,
):
    active_root = tmp_path / "active"
    (active_root / "SOS-DEMO").mkdir(parents=True)

    with pytest.raises(ValueError, match="active skill namespace collision"):
        validate_active_skill_namespace(
            active_root,
            source_skill_names=("alpha",),
            pointer_skill_names=("sos-demo",),
            managed_pointer_names=("sos-demo", COMPANION_POINTER_SKILL),
        )


def test_active_namespace_rejects_duplicate_existing_normalized_folder_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    active_root = tmp_path / "active"
    active_root.mkdir()

    class _FakeFolder:
        def __init__(self, name: str) -> None:
            self.name = name

        def is_dir(self) -> bool:
            return True

    original_iterdir = Path.iterdir

    def fake_iterdir(path: Path):
        if path == active_root:
            return iter((_FakeFolder("sos-demo"), _FakeFolder("SOS-DEMO")))
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    with pytest.raises(ValueError, match="active skill namespace collision"):
        validate_active_skill_namespace(
            active_root,
            source_skill_names=("alpha",),
            pointer_skill_names=("other-skill",),
            managed_pointer_names=(),
        )


def test_active_namespace_allows_existing_managed_pointer_folders(tmp_path: Path):
    active_root = tmp_path / "active"
    (active_root / "sos-demo").mkdir(parents=True)
    (active_root / COMPANION_POINTER_SKILL).mkdir(parents=True)

    validate_active_skill_namespace(
        active_root,
        source_skill_names=("alpha",),
        pointer_skill_names=("sos-demo",),
        managed_pointer_names=("sos-demo", COMPANION_POINTER_SKILL),
    )
