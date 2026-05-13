from __future__ import annotations

from pathlib import Path

from sos.path_safety import cross_platform_component_key, reject_component_collisions


COMPANION_POINTER_SKILL = "sos-haruhi"


def validate_active_skill_namespace(
    active_root: Path,
    *,
    source_skill_names: tuple[str, ...],
    pointer_skill_names: tuple[str, ...],
    managed_pointer_names: tuple[str, ...],
) -> None:
    reject_component_collisions(
        (*source_skill_names, *pointer_skill_names, COMPANION_POINTER_SKILL),
        "active skill namespace",
    )

    if not active_root.is_dir():
        return

    managed_pointer_keys = frozenset(
        cross_platform_component_key(pointer_name)
        for pointer_name in managed_pointer_names
    )
    existing_folder_names = {
        cross_platform_component_key(path.name): path.name
        for path in active_root.iterdir()
        if path.is_dir()
    }
    for pointer_name in (*pointer_skill_names, COMPANION_POINTER_SKILL):
        pointer_key = cross_platform_component_key(pointer_name)
        existing_name = existing_folder_names.get(pointer_key)
        if existing_name is not None and pointer_key not in managed_pointer_keys:
            raise ValueError(
                "active skill namespace collision: "
                f"{pointer_name!r} conflicts with existing active folder "
                f"{existing_name!r}"
            )
