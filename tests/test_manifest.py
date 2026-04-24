from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sos.manifest import (
    load_pack_manifest,
    load_registry,
    save_pack_manifest,
    save_registry,
    update_registry_after_apply,
    validate_registry,
)
from sos.models import (
    ActivationResult,
    OperationKind,
    PackManifest,
    Registry,
    SkillEntry,
    WriteOperation,
    WritePlan,
)
from sos.paths import RuntimePaths, expand_path
from sos.toml_io import atomic_write_text, read_toml, write_toml


def test_write_plan_uses_immutable_tuple_fields(tmp_path: Path):
    op = WriteOperation(OperationKind.COPY_SKILL, source=tmp_path / "a", target=tmp_path / "b")
    plan = WritePlan(plan_id="p1", pack_ids=("apify",), operations=(op,), requires_apply=True)

    assert plan.operations == (op,)
    with pytest.raises(FrozenInstanceError):
        plan.plan_id = "changed"


def test_write_operation_is_immutable(tmp_path: Path):
    op = WriteOperation(OperationKind.WRITE_MANIFEST, source=tmp_path / "a", target=tmp_path / "b")

    with pytest.raises(FrozenInstanceError):
        op.target = tmp_path / "changed"


def test_model_sequence_fields_are_isolated_from_external_list_mutation(tmp_path: Path):
    op = WriteOperation(OperationKind.COPY_SKILL, source=tmp_path / "a", target=tmp_path / "b")
    pack_ids = ["apify"]
    operations = [op]
    plan = WritePlan(plan_id="p1", pack_ids=pack_ids, operations=operations)

    pack_ids.append("obsidian")
    operations.append(WriteOperation(OperationKind.WRITE_MANIFEST, target=tmp_path / "manifest.toml"))

    assert plan.pack_ids == ("apify",)
    assert plan.operations == (op,)

    active_pointers = ["sos-apify"]
    registry = Registry(active_pointers=active_pointers)
    active_pointers.append("sos-obsidian")

    assert registry.active_pointers == ("sos-apify",)

    messages = ["ready"]
    result = ActivationResult(status="ready", pack_id="apify", messages=messages)
    messages.append("changed")

    assert result.messages == ("ready",)


def test_runtime_paths_default_to_global_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = RuntimePaths.default()

    assert paths.root == tmp_path / ".sos"
    assert paths.vault == tmp_path / ".sos" / "vault"
    assert paths.packs == tmp_path / ".sos" / "packs"
    assert paths.backups == tmp_path / ".sos" / "backups"
    assert paths.state == tmp_path / ".sos" / "state"


def test_runtime_paths_from_root_and_expand_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = RuntimePaths.from_root("~/project/.sos")

    assert paths.root == tmp_path / "project" / ".sos"
    assert paths.vault == paths.root / "vault"
    assert paths.packs == paths.root / "packs"
    assert paths.backups == paths.root / "backups"
    assert paths.state == paths.root / "state"
    assert expand_path("~/skills") == tmp_path / "skills"


def test_toml_write_round_trip_and_atomic_text(tmp_path: Path):
    target = tmp_path / "state" / "registry.toml"
    write_toml(target, {"packs": {"installed": ["apify"]}})
    assert read_toml(target)["packs"]["installed"] == ["apify"]

    atomic_write_text(target, 'packs = { installed = ["obsidian"] }\n')
    assert read_toml(target)["packs"]["installed"] == ["obsidian"]


def test_pack_manifest_round_trip_preserves_fingerprints_and_triggers(tmp_path: Path):
    manifest_path = tmp_path / "packs" / "work.toml"
    saved_path = tmp_path / "packs" / "work.saved.toml"
    manifest = PackManifest(
        id="work",
        display_name="Work",
        aliases=("work-pack",),
        description="Work skill pack.",
        pointer_skill="sos-work",
        sync_policy="clean-auto",
        vault_root=tmp_path / "vault" / "work",
        skills=(
            SkillEntry(
                name="work-skill",
                source_path=tmp_path / "source" / "work-skill",
                vault_path=tmp_path / "vault" / "work" / "work-skill",
                origin="codex",
                enabled_before_apply=False,
                last_source_fingerprint="sha256:source",
                last_vault_fingerprint="sha256:vault",
                last_synced_at="2026-04-24T15:28:00+08:00",
            ),
        ),
        triggers=({"term": "work", "reason": "Work automation tasks."},),
    )

    save_pack_manifest(manifest_path, manifest)
    loaded = load_pack_manifest(manifest_path)
    save_pack_manifest(saved_path, loaded)
    reloaded = load_pack_manifest(saved_path)

    assert reloaded.id == "work"
    assert reloaded.display_name == "Work"
    assert reloaded.aliases == ("work-pack",)
    assert reloaded.description == "Work skill pack."
    assert reloaded.pointer_skill == "sos-work"
    assert reloaded.sync_policy == "clean-auto"
    assert reloaded.vault_root == tmp_path / "vault" / "work"
    assert len(reloaded.skills) == 1
    skill = reloaded.skills[0]
    assert skill.name == "work-skill"
    assert skill.source_path == tmp_path / "source" / "work-skill"
    assert skill.vault_path == tmp_path / "vault" / "work" / "work-skill"
    assert skill.origin == "codex"
    assert skill.enabled_before_apply is False
    assert skill.last_source_fingerprint == "sha256:source"
    assert skill.last_vault_fingerprint == "sha256:vault"
    assert skill.last_synced_at == "2026-04-24T15:28:00+08:00"
    assert dict(reloaded.triggers[0]) == {"term": "work", "reason": "Work automation tasks."}


def test_registry_rejects_duplicate_aliases_and_pointer_names():
    registry = Registry(
        packs=(
            PackManifest(id="work-a", display_name="Work A", aliases=("work",), pointer_skill="sos-work"),
            PackManifest(id="work-b", display_name="Work B", aliases=("work",), pointer_skill="sos-work"),
        )
    )

    with pytest.raises(ValueError) as error:
        validate_registry(registry)

    message = str(error.value)
    assert "duplicate aliases" in message
    assert "work" in message
    assert "duplicate pointer skills" in message
    assert "sos-work" in message


def test_update_registry_after_apply_records_pointer_skill_names_from_skill_md_paths(tmp_path: Path):
    registry = Registry(backup_generations=("backup-001",))
    manifest = PackManifest(
        id="apify",
        display_name="Apify",
        aliases=("apify",),
        pointer_skill="sos-apify",
    )
    pointer_path = tmp_path / "skills" / "sos-apify" / "SKILL.md"

    updated = update_registry_after_apply(
        registry,
        (manifest,),
        (pointer_path,),
        "backup-002",
    )

    assert updated.active_pointers == ("sos-apify",)
    assert updated.backup_generations == ("backup-001", "backup-002")


def test_registry_supports_status_without_rescan(tmp_path: Path):
    registry_path = tmp_path / "state" / "registry.toml"
    missing_source = tmp_path / "missing-source" / "work-skill"
    missing_vault = tmp_path / "missing-vault" / "work-skill"
    registry = Registry(
        packs=(
            PackManifest(
                id="work",
                display_name="Work",
                aliases=("work-pack",),
                pointer_skill="sos-work",
                vault_root=tmp_path / "vault" / "work",
                skills=(
                    SkillEntry(
                        name="work-skill",
                        source_path=missing_source,
                        vault_path=missing_vault,
                    ),
                ),
            ),
        ),
        active_pointers=("sos-work",),
        aliases={"work": "work"},
        backup_generations=("backup-001", "backup-002"),
        last_operation_ids=("op-apply", "op-pointer"),
    )

    save_registry(registry_path, registry)
    loaded = load_registry(registry_path)

    assert not missing_source.exists()
    assert not missing_vault.exists()
    assert loaded.packs[0].id == "work"
    assert loaded.packs[0].skills[0].source_path == missing_source
    assert loaded.packs[0].skills[0].vault_path == missing_vault
    assert loaded.active_pointers == ("sos-work",)
    assert dict(loaded.aliases) == {"work": "work"}
    assert loaded.backup_generations == ("backup-001", "backup-002")
    assert loaded.last_operation_ids == ("op-apply", "op-pointer")
