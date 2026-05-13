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

    managed_pointer_name_set = frozenset(managed_pointer_names)
    existing_folder_names: dict[str, str] = {}
    for path in active_root.iterdir():
        if not path.is_dir():
            continue
        folder_key = cross_platform_component_key(path.name)
        existing_name = existing_folder_names.get(folder_key)
        if existing_name is not None:
            raise ValueError(
                "active skill namespace collision: "
                f"{existing_name!r} conflicts with existing active folder "
                f"{path.name!r}"
            )
        existing_folder_names[folder_key] = path.name

    for pointer_name in (*pointer_skill_names, COMPANION_POINTER_SKILL):
        pointer_key = cross_platform_component_key(pointer_name)
        existing_name = existing_folder_names.get(pointer_key)
        if (
            existing_name is not None
            and (
                existing_name != pointer_name
                or pointer_name not in managed_pointer_name_set
            )
        ):
            raise ValueError(
                "active skill namespace collision: "
                f"{pointer_name!r} conflicts with existing active folder "
                f"{existing_name!r}"
            )
