import json
from pathlib import Path

import pytest

import sos.recommendation_store as recommendation_store
from sos.paths import RuntimePaths


def test_stub_dry_run_does_not_write(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")

    path = recommendation_store.ensure_learned_reference_stub(runtime_paths, apply=False)

    assert path == runtime_paths.state / "recommendations" / "asahina-reference.md"
    assert not path.exists()


def test_stub_apply_writes_exact_empty_reference(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")

    path = recommendation_store.ensure_learned_reference_stub(runtime_paths, apply=True)

    assert path.read_text(encoding="utf-8") == recommendation_store.ASAHINA_EMPTY_REFERENCE


def test_append_load_round_trip_uses_compact_schema_without_forbidden_fields(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    event = recommendation_store.SelectionEvent(
        schema_version=1,
        created_at="2026-05-12T10:00:00+00:00",
        workspace_id="sha256:1234",
        scenario_label="apify crawler",
        scenario_tags=("apify", "crawler"),
        selected_pack_ids=("apify", "browser"),
        selected_skill_names=("crawl-site", "open-browser"),
        manifest_fingerprint="sha256:abcd",
        selection_source="activated",
        outcome="accepted",
    )

    path = recommendation_store.append_selection_event(runtime_paths, event)

    raw_text = path.read_text(encoding="utf-8")
    assert "raw_prompt" not in raw_text
    assert "file_contents" not in raw_text
    assert "model_messages" not in raw_text
    assert "account" not in raw_text

    line = json.loads(raw_text)
    assert set(line) == {
        "schema_version",
        "created_at",
        "workspace_id",
        "scenario_label",
        "scenario_tags",
        "selected_pack_ids",
        "selected_skill_names",
        "manifest_fingerprint",
        "selection_source",
        "outcome",
    }
    assert raw_text.endswith("\n")
    assert "  " not in raw_text

    loaded = recommendation_store.load_selection_events(runtime_paths)
    assert loaded == (event,)


def test_invalid_jsonl_lines_are_ignored_and_preserved(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    valid_line = json.dumps(
        {
            "schema_version": 1,
            "created_at": "2026-05-12T10:00:00+00:00",
            "workspace_id": "sha256:1234",
            "scenario_label": "apify crawler",
            "scenario_tags": ["apify"],
            "selected_pack_ids": ["apify"],
            "selected_skill_names": ["crawl-site"],
            "manifest_fingerprint": "sha256:abcd",
            "selection_source": "activated",
            "outcome": "accepted",
        },
        separators=(",", ":"),
    )
    original_text = "\n".join(
        [
            valid_line,
            "{not json}",
            json.dumps({"schema_version": 1, "created_at": "x"}, separators=(",", ":")),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(original_text, encoding="utf-8")

    loaded = recommendation_store.load_selection_events(runtime_paths)

    assert len(loaded) == 1
    assert loaded[0].scenario_label == "apify crawler"
    assert path.read_text(encoding="utf-8") == original_text


def test_ten_repeated_activated_selections_produce_learned_reference(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    event = recommendation_store.SelectionEvent(
        schema_version=1,
        created_at="2026-05-12T10:00:00+00:00",
        workspace_id="sha256:1234",
        scenario_label="apify crawler",
        scenario_tags=("apify", "crawler"),
        selected_pack_ids=("apify",),
        selected_skill_names=("crawl-site",),
        manifest_fingerprint="sha256:abcd",
        selection_source="activated",
        outcome="accepted",
    )
    path = recommendation_store.selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": event.schema_version,
                    "created_at": f"2026-05-12T10:00:0{index}+00:00",
                    "workspace_id": event.workspace_id,
                    "scenario_label": event.scenario_label,
                    "scenario_tags": list(event.scenario_tags),
                    "selected_pack_ids": list(event.selected_pack_ids),
                    "selected_skill_names": list(event.selected_skill_names),
                    "manifest_fingerprint": event.manifest_fingerprint,
                    "selection_source": event.selection_source,
                    "outcome": event.outcome,
                },
                separators=(",", ":"),
            )
            + "\n"
            for index in range(10)
        ),
        encoding="utf-8",
    )

    reference = recommendation_store.build_learned_reference(
        recommendation_store.load_selection_events(runtime_paths)
    )

    assert reference != recommendation_store.ASAHINA_EMPTY_REFERENCE
    assert "## Learned Recommendation Hints" in reference
    assert "Scenario: apify crawler" in reference
    assert "Prefer recommending: apify" in reference
    assert "Evidence: 10 accepted selections" in reference


def test_below_threshold_returns_empty_reference(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    event = recommendation_store.SelectionEvent(
        schema_version=1,
        created_at="2026-05-12T10:00:00+00:00",
        workspace_id="sha256:1234",
        scenario_label="apify crawler",
        scenario_tags=("apify",),
        selected_pack_ids=("apify",),
        selected_skill_names=("crawl-site",),
        manifest_fingerprint="sha256:abcd",
        selection_source="activated",
        outcome="accepted",
    )
    path = recommendation_store.selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "schema_version": event.schema_version,
                    "created_at": f"2026-05-12T10:00:0{index}+00:00",
                    "workspace_id": event.workspace_id,
                    "scenario_label": event.scenario_label,
                    "scenario_tags": list(event.scenario_tags),
                    "selected_pack_ids": list(event.selected_pack_ids),
                    "selected_skill_names": list(event.selected_skill_names),
                    "manifest_fingerprint": event.manifest_fingerprint,
                    "selection_source": event.selection_source,
                    "outcome": event.outcome,
                },
                separators=(",", ":"),
            )
            for index in range(9)
        )
        + "\n",
        encoding="utf-8",
    )

    reference = recommendation_store.build_learned_reference(
        recommendation_store.load_selection_events(runtime_paths)
    )

    assert reference == recommendation_store.ASAHINA_EMPTY_REFERENCE


def test_learned_reference_write_is_dry_run_unless_apply_true(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    reference = "# Learned Recommendation Hints\n\nScenario: x\n"

    path = recommendation_store.write_learned_reference(
        runtime_paths,
        reference,
        apply=False,
    )

    assert path == runtime_paths.state / "recommendations" / "asahina-reference.md"
    assert not path.exists()

    written = recommendation_store.write_learned_reference(
        runtime_paths,
        reference,
        apply=True,
    )

    assert written.read_text(encoding="utf-8") == reference


def test_workspace_id_is_stable_and_hides_raw_path(tmp_path: Path):
    path = tmp_path / "nested" / ".." / "workspace"

    first = recommendation_store.workspace_id_for_path(path)
    second = recommendation_store.workspace_id_for_path(path)

    assert first == second
    assert first.startswith("sha256:")
    assert str(path.resolve()) not in first

