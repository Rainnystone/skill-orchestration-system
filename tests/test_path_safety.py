"""Tests for sos.path_safety -- SF5 exact-duplicate collision rejection and
SF4 Windows reserved name + trailing dot/space blocking."""

from pathlib import Path

import pytest

from sos.path_safety import (
    reject_component_collisions,
    reject_path_collisions,
    safe_component,
)


# ---------------------------------------------------------------------------
# SF5: reject exact duplicates in collision helpers
# ---------------------------------------------------------------------------

def test_reject_component_collisions_rejects_exact_duplicate():
    """Exact duplicate components ("alpha", "alpha") must raise ValueError."""
    with pytest.raises(ValueError):
        reject_component_collisions(("alpha", "alpha"), "test_label")


def test_reject_path_collisions_rejects_exact_duplicate():
    """Exact duplicate paths (Path("/a/b"), Path("/a/b")) must raise ValueError."""
    with pytest.raises(ValueError):
        reject_path_collisions((Path("/a/b"), Path("/a/b")), "test_label")


# ---------------------------------------------------------------------------
# SF4: block Windows reserved names and trailing dot/space in safe_component()
# ---------------------------------------------------------------------------

_RESERVED_CASES = [
    "CON",
    "con",
    "COM1",
    "LPT9",
    "NUL",
    "PRN",
    "AUX",
]


@pytest.mark.parametrize("name", _RESERVED_CASES)
def test_safe_component_rejects_windows_reserved(name: str):
    """Windows reserved device names (case-insensitive) must be rejected."""
    with pytest.raises(ValueError):
        safe_component(name, "x")


_TRAILING_CASES = [
    ("trailing dot", "skill."),
    ("trailing space", "skill "),
]


@pytest.mark.parametrize("_desc,name", _TRAILING_CASES)
def test_safe_component_rejects_trailing(_desc: str, name: str):
    """Names ending with a dot or space must be rejected."""
    with pytest.raises(ValueError):
        safe_component(name, "x")


def test_safe_component_accepts_normal_name():
    """A normal safe name should be returned unchanged."""
    assert safe_component("normal-skill", "x") == "normal-skill"


def test_reject_component_collisions_rejects_pointer_skills():
    """Pointer skill names that collide by casefold must be caught with
    an explicit 'pointer_skill collision' message."""
    with pytest.raises(ValueError, match="pointer_skill collision"):
        reject_component_collisions(("sos-Demo", "sos-demo"), "pointer_skill")


# ---------------------------------------------------------------------------
# Fix 1: colon and reserved names with extensions in safe_component()
# ---------------------------------------------------------------------------

def test_safe_component_rejects_colon_in_name():
    """Colon is illegal on NTFS and must be rejected."""
    with pytest.raises(ValueError, match="unsafe x"):
        safe_component("a:b", "x")


def test_safe_component_rejects_reserved_name_with_extension():
    """Reserved Windows names with extensions like CON.txt must be rejected."""
    with pytest.raises(ValueError, match="unsafe x"):
        safe_component("CON.txt", "x")


def test_safe_component_rejects_lpt_with_extension():
    """LPT1.md must be rejected as a reserved name with extension."""
    with pytest.raises(ValueError, match="unsafe x"):
        safe_component("LPT1.md", "x")


def test_safe_component_rejects_nul_with_extension():
    """NUL.skill must be rejected as a reserved name with extension."""
    with pytest.raises(ValueError, match="unsafe x"):
        safe_component("NUL.skill", "x")


def test_safe_component_rejects_reserved_case_insensitive_with_extension():
    """com1.backup must be rejected case-insensitively."""
    with pytest.raises(ValueError, match="unsafe x"):
        safe_component("com1.backup", "x")


def test_safe_component_accepts_normal_name_with_extension():
    """normal.txt is a safe name with extension and must be accepted."""
    assert safe_component("normal.txt", "x") == "normal.txt"
