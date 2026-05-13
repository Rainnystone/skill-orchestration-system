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
    if value.rstrip(". ").casefold() in _WINDOWS_RESERVED_NAMES:
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
