from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


class OperationKind(StrEnum):
    COPY_SKILL = "copy_skill"
    WRITE_MANIFEST = "write_manifest"
    WRITE_REGISTRY = "write_registry"
    WRITE_POINTER = "write_pointer"
    BACKUP_CODEX_CONFIG = "backup_codex_config"
    DISABLE_CODEX_SKILL = "disable_codex_skill"
    DELETE_SOURCE = "delete_source"
    BACKUP_VAULT = "backup_vault"
    RESTORE_CONFIG = "restore_config"
    RESTORE_VAULT = "restore_vault"


@dataclass(frozen=True)
class WriteOperation:
    kind: OperationKind
    source: Path | None = None
    target: Path | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class WritePlan:
    plan_id: str
    pack_ids: tuple[str, ...] = ()
    operations: tuple[WriteOperation, ...] = ()
    requires_apply: bool = False
    delete_source_requested: bool = False
    second_confirmation: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_ids", tuple(self.pack_ids))
        object.__setattr__(self, "operations", tuple(self.operations))


@dataclass(frozen=True)
class SkillEntry:
    name: str
    source_path: Path
    vault_path: Path
    origin: str = ""
    enabled_before_apply: bool = True
    last_source_fingerprint: str = ""
    last_vault_fingerprint: str = ""
    last_synced_at: str = ""


@dataclass(frozen=True)
class PackManifest:
    id: str
    display_name: str
    pointer_skill: str
    skills: tuple[SkillEntry, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""
    triggers: tuple[Mapping[str, str], ...] = ()
    sync_policy: str = "clean-auto"
    vault_root: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", tuple(self.skills))
        object.__setattr__(self, "aliases", tuple(self.aliases))
        frozen_triggers = tuple(_freeze_mapping(trigger) for trigger in self.triggers)
        object.__setattr__(self, "triggers", frozen_triggers)


@dataclass(frozen=True)
class Registry:
    packs: tuple[PackManifest, ...] = ()
    active_pointers: tuple[str, ...] = ()
    aliases: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    backup_generations: tuple[str, ...] = ()
    last_operation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "packs", tuple(self.packs))
        object.__setattr__(self, "active_pointers", tuple(self.active_pointers))
        object.__setattr__(self, "aliases", _freeze_mapping(self.aliases))
        object.__setattr__(self, "backup_generations", tuple(self.backup_generations))
        object.__setattr__(self, "last_operation_ids", tuple(self.last_operation_ids))


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    created_at: datetime
    config_path: Path | None = None
    vault_path: Path | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True)
class ActivationResult:
    status: str
    pack_id: str
    manifest_path: Path | None = None
    messages: tuple[str, ...] = ()
    operations: tuple[WriteOperation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "operations", tuple(self.operations))
