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
