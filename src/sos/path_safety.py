from __future__ import annotations

import unicodedata
from pathlib import Path


_WINDOWS_RESERVED_NAMES = frozenset({
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{d}" for d in range(1, 10)),
    *(f"lpt{d}" for d in range(1, 10)),
})


def safe_component(value: str, label: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
        or Path(value).name != value
    ):
        raise ValueError(f"unsafe {label}: {value}")
    if ":" in value:
        raise ValueError(f"unsafe {label}: {value}")
    trimmed = value.rstrip(". ")
    stem = trimmed.split(".")[0]
    if stem.casefold() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"unsafe {label}: {value}")
    if value != value.rstrip(". "):
        raise ValueError(f"unsafe {label}: {value}")
    return value


def cross_platform_component_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def cross_platform_path_key(path: Path) -> str:
    return unicodedata.normalize("NFC", path.resolve(strict=False).as_posix()).casefold()


def reject_component_collisions(values: tuple[str, ...], label: str) -> None:
    seen: dict[str, str] = {}
    for value in values:
        key = cross_platform_component_key(value)
        existing = seen.get(key)
        if existing is not None:
            raise ValueError(f"{label} collision: {existing!r} and {value!r}")
        seen[key] = value


def reject_path_collisions(paths: tuple[Path, ...], label: str) -> None:
    seen: dict[str, Path] = {}
    for path in paths:
        key = cross_platform_path_key(path)
        existing = seen.get(key)
        if existing is not None:
            raise ValueError(f"{label} collision: {existing!r} and {path!r}")
        seen[key] = path


def safe_pointer_skill(value: str) -> str:
    """Validate a pointer skill name (must start with 'sos-' and be a safe component)."""
    safe_component(value, "pointer_skill")
    if not value.startswith("sos-"):
        raise ValueError(f"unsafe pointer_skill: {value}")
    return value


def ensure_under(path: Path, root: Path, label: str) -> None:
    """Raise ValueError if *path* does not live under *root*."""
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root):
        return
    raise ValueError(f"{label} escapes expected root: {path}")


def required_path(path: Path | None) -> Path:
    """Return *path* or raise ValueError if it is None."""
    if path is None:
        raise ValueError("operation path is required")
    return path
