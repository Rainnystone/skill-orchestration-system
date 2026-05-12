import json
from pathlib import Path

import pytest

import sos.recommendation_store as recommendation_store
from sos.paths import RuntimePaths


def _selection_event(**overrides: object) -> recommendation_store.SelectionEvent:
    payload: dict[str, object] = {
        "schema_version": 1,
        "created_at": "2026-05-12T10:00:00+00:00",
        "workspace_id": "sha256:1234",
        "scenario_label": "docs planning",
        "scenario_tags": ("docs", "planning"),
        "selected_pack_ids": ("docs",),
        "selected_skill_names": ("documents",),
        "manifest_fingerprint": "sha256:abcd",
        "selection_source": "user_accepted",
        "outcome": "activated",
    }
    payload.update(overrides)
    return recommendation_store.SelectionEvent(**payload)


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
    event = _selection_event(
        scenario_label="apify crawler",
        scenario_tags=("apify", "crawler"),
        selected_pack_ids=("apify", "browser"),
        selected_skill_names=("crawl-site", "open-browser"),
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


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"scenario_label": r"C:\Users\private\notes"}, "unsafe scenario_label"),
        ({"scenario_label": "workspace\ndocs"}, "unsafe scenario_label"),
        ({"scenario_label": "x" * 81}, "unsafe scenario_label"),
        (
            {
                "scenario_label": "please summarize secret board deck",
                "scenario_tags": ("docs", "deck"),
            },
            "unsafe scenario_label",
        ),
        ({"scenario_tags": ("docs", "")}, "unsafe scenario_tag"),
        ({"scenario_tags": ("docs", "private/path")}, "unsafe scenario_tag"),
        ({"selected_pack_ids": ("docs", "docs")}, "unsafe selected_pack_id"),
        ({"selected_skill_names": ("documents", "documents")}, "unsafe selected_skill_name"),
        ({"selected_pack_ids": ("docs", "docs/private")}, "unsafe selected_pack_id"),
        ({"selected_skill_names": ("documents", r"open\browser")}, "unsafe selected_skill_name"),
    ),
)
def test_append_selection_event_rejects_unsafe_values_before_write(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")

    with pytest.raises(ValueError, match=message):
        recommendation_store.append_selection_event(
            runtime_paths,
            _selection_event(**overrides),
        )

    assert not recommendation_store.selection_events_path(runtime_paths).exists()


def test_invalid_jsonl_lines_are_ignored_and_preserved(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    valid_line = json.dumps(
        {
            "schema_version": 1,
            "created_at": "2026-05-12T10:00:00+00:00",
            "workspace_id": "sha256:1234",
            "scenario_label": "apify crawler",
            "scenario_tags": ["apify", "crawler"],
            "selected_pack_ids": ["apify"],
            "selected_skill_names": ["crawl-site"],
            "manifest_fingerprint": "sha256:abcd",
            "selection_source": "user_accepted",
            "outcome": "activated",
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


def test_loaded_selection_events_ignore_invalid_persisted_values(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    valid_line = json.dumps(
        recommendation_store._selection_event_payload(_selection_event()),
        separators=(",", ":"),
    )
    invalid_lines = (
        json.dumps(
            recommendation_store._selection_event_payload(
                _selection_event(scenario_label=r"C:\Users\private\prompt")
            ),
            separators=(",", ":"),
        ),
        json.dumps(
            recommendation_store._selection_event_payload(
                _selection_event(scenario_tags=("docs", ""))
            ),
            separators=(",", ":"),
        ),
    )
    original_text = "\n".join((valid_line, *invalid_lines, ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(original_text, encoding="utf-8")

    loaded = recommendation_store.load_selection_events(runtime_paths)

    assert loaded == (_selection_event(),)
    assert path.read_text(encoding="utf-8") == original_text


def test_ten_repeated_activated_selections_produce_learned_reference(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    event = _selection_event(
        scenario_label="apify crawler",
        scenario_tags=("apify", "crawler"),
        selected_pack_ids=("apify",),
        selected_skill_names=("crawl-site",),
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
    assert "Workspace: sha256:1234" in reference
    assert "Scenario: apify crawler" in reference
    assert "Scenario tags: apify, crawler" in reference
    assert "Prefer recommending: apify" in reference
    assert "Evidence: 10 accepted selections" in reference


def test_learned_reference_preserves_multiple_eligible_workspace_blocks():
    events: list[recommendation_store.SelectionEvent] = []
    for index in range(10):
        events.append(
            _selection_event(
                created_at=f"2026-05-12T10:00:0{index}+00:00",
                workspace_id="sha256:docs-workspace",
                scenario_label="docs planning",
                scenario_tags=("docs", "planning"),
                selected_pack_ids=("docs",),
                selected_skill_names=("documents",),
            )
        )
        events.append(
            _selection_event(
                created_at=f"2026-05-12T10:01:0{index}+00:00",
                workspace_id="sha256:browser-workspace",
                scenario_label="browser",
                scenario_tags=("browser",),
                selected_pack_ids=("browser",),
                selected_skill_names=("open-browser",),
            )
        )

    reference = recommendation_store.build_learned_reference(events)

    assert reference.count("Workspace: ") == 2
    assert "Workspace: sha256:docs-workspace" in reference
    assert "Scenario tags: docs, planning" in reference
    assert "Prefer recommending: docs" in reference
    assert "Workspace: sha256:browser-workspace" in reference
    assert "Scenario tags: browser" in reference
    assert "Prefer recommending: browser" in reference


def test_learned_reference_canonicalizes_pack_order_for_counts():
    events: list[recommendation_store.SelectionEvent] = []
    for index in range(5):
        events.append(
            _selection_event(
                created_at=f"2026-05-12T10:00:0{index}+00:00",
                scenario_label="browser docs",
                scenario_tags=("browser", "docs"),
                selected_pack_ids=("browser", "docs"),
                selected_skill_names=("open-browser", "documents"),
            )
        )
        events.append(
            _selection_event(
                created_at=f"2026-05-12T10:01:0{index}+00:00",
                scenario_label="browser docs",
                scenario_tags=("browser", "docs"),
                selected_pack_ids=("docs", "browser"),
                selected_skill_names=("documents", "open-browser"),
            )
        )

    reference = recommendation_store.build_learned_reference(events)

    assert reference != recommendation_store.ASAHINA_EMPTY_REFERENCE
    assert "Prefer recommending: browser, docs" in reference
    assert "Evidence: 10 accepted selections" in reference


def test_learned_reference_canonicalizes_tag_order_for_counts():
    events: list[recommendation_store.SelectionEvent] = []
    for index in range(5):
        events.append(
            _selection_event(
                created_at=f"2026-05-12T10:00:0{index}+00:00",
                scenario_label="docs browser",
                scenario_tags=("docs", "browser"),
                selected_pack_ids=("browser", "docs"),
                selected_skill_names=("open-browser", "documents"),
            )
        )
        events.append(
            _selection_event(
                created_at=f"2026-05-12T10:01:0{index}+00:00",
                scenario_label="browser docs",
                scenario_tags=("browser", "docs"),
                selected_pack_ids=("docs", "browser"),
                selected_skill_names=("documents", "open-browser"),
            )
        )

    reference = recommendation_store.build_learned_reference(events)

    assert reference != recommendation_store.ASAHINA_EMPTY_REFERENCE
    assert "Scenario: browser docs" in reference
    assert "Scenario tags: browser, docs" in reference
    assert "Prefer recommending: browser, docs" in reference
    assert "Evidence: 10 accepted selections" in reference


def test_learned_reference_does_not_merge_events_from_different_workspaces(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                recommendation_store._selection_event_payload(
                    _selection_event(
                        created_at=f"2026-05-12T10:00:0{index}+00:00",
                        workspace_id="sha256:one" if index < 5 else "sha256:two",
                    )
                ),
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

    assert reference == recommendation_store.ASAHINA_EMPTY_REFERENCE


def test_learned_reference_does_not_merge_events_with_different_tag_sets(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                recommendation_store._selection_event_payload(
                    _selection_event(
                        created_at=f"2026-05-12T10:00:0{index}+00:00",
                        scenario_tags=("docs", "planning")
                        if index < 5
                        else ("docs", "review"),
                    )
                ),
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

    assert reference == recommendation_store.ASAHINA_EMPTY_REFERENCE


def test_old_reversed_semantics_do_not_count_toward_learned_reference(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": 1,
                    "created_at": f"2026-05-12T10:00:0{index}+00:00",
                    "workspace_id": "sha256:1234",
                    "scenario_label": "apify crawler",
                    "scenario_tags": ["apify", "crawler"],
                    "selected_pack_ids": ["apify"],
                    "selected_skill_names": ["crawl-site"],
                    "manifest_fingerprint": "sha256:abcd",
                    "selection_source": "activated",
                    "outcome": "accepted",
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

    assert reference == recommendation_store.ASAHINA_EMPTY_REFERENCE


def test_unsupported_schema_versions_are_ignored(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    path = recommendation_store.selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": 999,
                    "created_at": f"2026-05-12T10:00:0{index}+00:00",
                    "workspace_id": "sha256:1234",
                    "scenario_label": "apify crawler",
                    "scenario_tags": ["apify", "crawler"],
                    "selected_pack_ids": ["apify"],
                    "selected_skill_names": ["crawl-site"],
                    "manifest_fingerprint": "sha256:abcd",
                    "selection_source": "user_accepted",
                    "outcome": "activated",
                },
                separators=(",", ":"),
            )
            + "\n"
            for index in range(10)
        ),
        encoding="utf-8",
    )

    loaded_events = recommendation_store.load_selection_events(runtime_paths)
    reference = recommendation_store.build_learned_reference(loaded_events)

    assert loaded_events == ()
    assert reference == recommendation_store.ASAHINA_EMPTY_REFERENCE


def test_below_threshold_returns_empty_reference(tmp_path: Path):
    runtime_paths = RuntimePaths.from_root(tmp_path / ".sos")
    event = _selection_event(
        scenario_label="apify crawler",
        scenario_tags=("apify", "crawler"),
        selected_pack_ids=("apify",),
        selected_skill_names=("crawl-site",),
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
