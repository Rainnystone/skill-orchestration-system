"""Host adapter seam.

Concentrates host-specific behaviour (Codex config-write vs Claude archive-move)
behind a polymorphic interface so that planner, apply, and cli no longer branch
on ``if host == "codex"`` / ``if host == "claude"`` throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sos._archive import ARCHIVE_DIR_NAME, ArchiveMove, execute_move_to_archive
from sos.backups import record_claude_archive_restore_entries
from sos.codex_config import disable_skill_paths_with_backup
from sos.host_paths import validate_host
from sos.models import (
    OperationKind,
    PackManifest,
    SkillEntry,
    WriteOperation,
    WritePlan,
)
from sos.paths import RuntimePaths
from sos.path_safety import ensure_under, required_path, safe_component, safe_pointer_skill
from sos.plan_ops import operations_of_kind, single_operation


@dataclass(frozen=True)
class HostValidation:
    """Result of host-specific plan validation."""

    disabled_skill_md_paths: tuple[Path, ...] = ()
    archive_operations: tuple[WriteOperation, ...] = ()


class HostAdapter:
    """Abstract host adapter.  Subclasses implement host-specific behaviour."""

    host: str = ""
    requires_codex_config: bool = False

    # -- Planning -----------------------------------------------------------

    def plan_backup_operations(
        self,
        runtime_paths: RuntimePaths,
        plan_id: str,
        config_path: Path,
    ) -> tuple[WriteOperation, ...]:
        """Operations for phase 0 (backup config/vault)."""
        raise NotImplementedError

    def plan_disable_operations(
        self,
        config_path: Path,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> tuple[WriteOperation, ...]:
        """Operations for phase 5 (disable/archive source skills)."""
        raise NotImplementedError

    def delete_source_target(
        self,
        active_root: Path,
        manifest: PackManifest,
        skill: SkillEntry,
    ) -> Path:
        raise NotImplementedError

    # -- Execution ----------------------------------------------------------

    def execute_disable(
        self,
        plan: WritePlan,
        config_path: Path,
        backup_config_path: Path | None,
        disabled_skill_md_paths: tuple[Path, ...],
        archive_journal: list[ArchiveMove],
    ) -> dict[Path, Path]:
        """Execute host-specific disable/archive operations.

        Returns an ``archive_map`` (source -> target) for fingerprint baselining.
        """
        raise NotImplementedError

    def post_apply(
        self,
        runtime_paths: RuntimePaths,
        backup_id: str,
        manifests: tuple[PackManifest, ...],
    ) -> None:
        """Hook called after successful apply (e.g. record archive restore entries)."""
        pass

    # -- Validation ---------------------------------------------------------

    def validate_host_plan(
        self,
        plan: WritePlan,
        runtime_paths: RuntimePaths,
        config_path: Path,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> HostValidation:
        raise NotImplementedError

    def expected_delete_targets(
        self,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> tuple[tuple[Path, str, str], ...]:
        raise NotImplementedError

    # -- CLI helpers --------------------------------------------------------

    def config_path_from_plan(self, plan: WritePlan, active_root: Path) -> Path:
        raise NotImplementedError

    def annotate_backup_metadata(self, config_path: Path) -> dict[str, Any]:
        return {}

    def restore_targets_from_metadata(
        self,
        metadata: dict[str, Any],
    ) -> tuple[Path | None, Path | None]:
        """Return ``(codex_config_path, vault_root)`` from backup metadata."""
        vault_root_str = metadata.get("vault_root")
        vault_root = Path(str(vault_root_str)) if vault_root_str else None
        return None, vault_root


class CodexHostAdapter(HostAdapter):
    host = "codex"
    requires_codex_config = True

    def plan_backup_operations(
        self,
        runtime_paths: RuntimePaths,
        plan_id: str,
        config_path: Path,
    ) -> tuple[WriteOperation, ...]:
        return (_backup_config_operation(runtime_paths, plan_id, config_path),)

    def plan_disable_operations(
        self,
        config_path: Path,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> tuple[WriteOperation, ...]:
        return _disable_config_operations(config_path, manifests)

    def delete_source_target(
        self,
        active_root: Path,
        manifest: PackManifest,
        skill: SkillEntry,
    ) -> Path:
        return skill.source_path

    def execute_disable(
        self,
        plan: WritePlan,
        config_path: Path,
        backup_config_path: Path | None,
        disabled_skill_md_paths: tuple[Path, ...],
        archive_journal: list[ArchiveMove],
    ) -> dict[Path, Path]:
        if backup_config_path is None:
            raise ValueError("backup_config_path is required for codex host")
        disable_skill_paths_with_backup(
            config_path,
            disabled_skill_md_paths,
            backup_path=backup_config_path,
            apply=True,
        )
        return {}

    def validate_host_plan(
        self,
        plan: WritePlan,
        runtime_paths: RuntimePaths,
        config_path: Path,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> HostValidation:
        from sos.path_safety import ensure_under, required_path
        from sos.plan_ops import operations_of_kind, single_operation

        backup_config = single_operation(plan, OperationKind.BACKUP_CODEX_CONFIG)
        backup_vault = single_operation(plan, OperationKind.BACKUP_VAULT)
        if required_path(backup_config.source) != config_path:
            raise ValueError("backup config source does not match codex_config_path")
        ensure_under(
            required_path(backup_config.target),
            runtime_paths.backups,
            "config backup target path",
        )
        if required_path(backup_vault.source) != runtime_paths.vault:
            raise ValueError("backup vault source does not match runtime vault")
        ensure_under(
            required_path(backup_vault.target),
            runtime_paths.backups,
            "vault backup target path",
        )

        disabled_skill_md_paths = _validate_disable_operations(
            plan, active_root, config_path, manifests
        )
        return HostValidation(
            disabled_skill_md_paths=disabled_skill_md_paths,
            archive_operations=(),
        )

    def expected_delete_targets(
        self,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> tuple[tuple[Path, str, str], ...]:
        return tuple(
            (skill.source_path, manifest.id, skill.name)
            for manifest in manifests
            for skill in manifest.skills
        )

    def config_path_from_plan(self, plan: WritePlan, active_root: Path) -> Path:
        from sos.path_safety import required_path
        from sos.plan_ops import single_operation

        backup_config = single_operation(plan, OperationKind.BACKUP_CODEX_CONFIG)
        return required_path(backup_config.source)

    def annotate_backup_metadata(self, config_path: Path) -> dict[str, Any]:
        return {"codex_config_path": str(config_path)}

    def restore_targets_from_metadata(
        self,
        metadata: dict[str, Any],
    ) -> tuple[Path | None, Path | None]:
        codex_config_path = Path(str(metadata["codex_config_path"]))
        vault_root_str = metadata.get("vault_root")
        vault_root = Path(str(vault_root_str)) if vault_root_str else None
        return codex_config_path, vault_root


class ClaudeHostAdapter(HostAdapter):
    host = "claude"
    requires_codex_config = False

    def plan_backup_operations(
        self,
        runtime_paths: RuntimePaths,
        plan_id: str,
        config_path: Path,
    ) -> tuple[WriteOperation, ...]:
        return ()

    def plan_disable_operations(
        self,
        config_path: Path,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> tuple[WriteOperation, ...]:
        return _move_to_archive_operations(active_root, manifests, self.host)

    def delete_source_target(
        self,
        active_root: Path,
        manifest: PackManifest,
        skill: SkillEntry,
    ) -> Path:
        return active_root / ARCHIVE_DIR_NAME / manifest.id / skill.name

    def execute_disable(
        self,
        plan: WritePlan,
        config_path: Path,
        backup_config_path: Path | None,
        disabled_skill_md_paths: tuple[Path, ...],
        archive_journal: list[ArchiveMove],
    ) -> dict[Path, Path]:
        from sos.path_safety import required_path
        from sos.plan_ops import operations_of_kind

        archive_map: dict[Path, Path] = {}
        for operation in operations_of_kind(plan, OperationKind.MOVE_TO_ARCHIVE):
            execute_move_to_archive(operation, archive_journal)
            archive_map[required_path(operation.source)] = required_path(operation.target)
        return archive_map

    def post_apply(
        self,
        runtime_paths: RuntimePaths,
        backup_id: str,
        manifests: tuple[PackManifest, ...],
    ) -> None:
        record_claude_archive_restore_entries(runtime_paths, backup_id, manifests)

    def validate_host_plan(
        self,
        plan: WritePlan,
        runtime_paths: RuntimePaths,
        config_path: Path,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> HostValidation:
        from sos.apply import _validate_archive_operations
        from sos.path_safety import ensure_under, required_path
        from sos.plan_ops import single_operation

        backup_vault = single_operation(plan, OperationKind.BACKUP_VAULT)
        if required_path(backup_vault.source) != runtime_paths.vault:
            raise ValueError("backup vault source does not match runtime vault")
        ensure_under(
            required_path(backup_vault.target),
            runtime_paths.backups,
            "vault backup target path",
        )

        archive_operations = _validate_archive_operations(plan, active_root, manifests)
        return HostValidation(
            disabled_skill_md_paths=(),
            archive_operations=archive_operations,
        )

    def expected_delete_targets(
        self,
        active_root: Path,
        manifests: tuple[PackManifest, ...],
    ) -> tuple[tuple[Path, str, str], ...]:
        return tuple(
            (active_root / ARCHIVE_DIR_NAME / manifest.id / skill.name, manifest.id, skill.name)
            for manifest in manifests
            for skill in manifest.skills
        )

    def config_path_from_plan(self, plan: WritePlan, active_root: Path) -> Path:
        return active_root / ".sos-no-codex-config"

    def annotate_backup_metadata(self, config_path: Path) -> dict[str, Any]:
        return {}

    def restore_targets_from_metadata(
        self,
        metadata: dict[str, Any],
    ) -> tuple[Path | None, Path | None]:
        vault_root_str = metadata.get("vault_root")
        vault_root = Path(str(vault_root_str)) if vault_root_str else None
        return None, vault_root


def host_adapter_for(host: str) -> HostAdapter:
    safe_host = validate_host(host)
    if safe_host == "codex":
        return CodexHostAdapter()
    if safe_host == "claude":
        return ClaudeHostAdapter()
    raise ValueError(f"unsupported host: {host}")


# ---------------------------------------------------------------------------
# Planning helpers (moved from planner.py)
# ---------------------------------------------------------------------------

def _backup_config_operation(
    runtime_paths: RuntimePaths,
    plan_id: str,
    config_path: Path,
) -> WriteOperation:
    from sos.path_safety import safe_component  # noqa: F401 — already validated upstream
    backup_target = runtime_paths.backups / plan_id / "config.toml"
    ensure_under(backup_target, runtime_paths.backups, "config backup target path")
    return WriteOperation(
        OperationKind.BACKUP_CODEX_CONFIG,
        source=config_path,
        target=backup_target,
        metadata={
            "backup_id": plan_id,
            "codex_config_path": str(config_path),
            "reason": "pack apply",
        },
    )


def _disable_config_operations(
    config_path: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[WriteOperation, ...]:
    return tuple(
        WriteOperation(
            OperationKind.DISABLE_CODEX_SKILL,
            source=skill.source_path / "SKILL.md",
            target=config_path,
            metadata={
                "pack_id": manifest.id,
                "skill_name": skill.name,
                "skill_md_path": str(skill.source_path / "SKILL.md"),
            },
        )
        for manifest in manifests
        for skill in manifest.skills
    )


def _move_to_archive_operations(
    active_root: Path,
    manifests: tuple[PackManifest, ...],
    host: str,
) -> tuple[WriteOperation, ...]:
    return tuple(
        _move_to_archive_operation(active_root, manifest, skill, host)
        for manifest in manifests
        for skill in manifest.skills
    )


def _move_to_archive_operation(
    active_root: Path,
    manifest: PackManifest,
    skill: SkillEntry,
    host: str,
) -> WriteOperation:
    archive_target = active_root / ARCHIVE_DIR_NAME / manifest.id / skill.name
    ensure_under(skill.source_path, active_root, "archive source path")
    ensure_under(archive_target, active_root, "archive target path")
    return WriteOperation(
        OperationKind.MOVE_TO_ARCHIVE,
        source=skill.source_path,
        target=archive_target,
        metadata={
            "pack_id": manifest.id,
            "skill_name": skill.name,
            "host": host,
        },
    )


# ---------------------------------------------------------------------------
# Validation helpers (moved from apply.py)
# ---------------------------------------------------------------------------

def _validate_disable_operations(
    plan: WritePlan,
    active_root: Path,
    config_path: Path,
    manifests: tuple[PackManifest, ...],
) -> tuple[Path, ...]:
    from sos.path_safety import required_path
    from sos.plan_ops import operations_of_kind

    expected_paths = tuple(
        skill.source_path / "SKILL.md"
        for manifest in manifests
        for skill in manifest.skills
    )
    operations = operations_of_kind(plan, OperationKind.DISABLE_CODEX_SKILL)
    actual_paths = tuple(required_path(operation.source) for operation in operations)
    if actual_paths != expected_paths:
        raise ValueError("config disable operations do not match manifest skills")

    for operation, skill_md_path in zip(operations, actual_paths, strict=True):
        ensure_under(skill_md_path, active_root, "config disable source path")
        if required_path(operation.target) != config_path:
            raise ValueError("config disable target does not match codex_config_path")
        metadata_path = operation.metadata.get("skill_md_path")
        if metadata_path is not None and Path(str(metadata_path)) != skill_md_path:
            raise ValueError("config disable metadata path does not match source")
    return actual_paths
