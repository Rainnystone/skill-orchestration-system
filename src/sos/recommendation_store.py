from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from sos.paths import RuntimePaths
from sos.toml_io import atomic_write_text


ASAHINA_EMPTY_REFERENCE = (
    "# SOS Asahina Learned Reference\n\n"
    "Status: empty\n\n"
    "No learned recommendations have been approved yet.\n"
)

_RECOMMENDATIONS_DIRNAME = "recommendations"
_SELECTION_EVENTS_FILENAME = "selection-events.jsonl"
_LEARNED_REFERENCE_FILENAME = "asahina-reference.md"
_MAX_SCENARIO_LABEL_LENGTH = 80
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,63})?$")
_SELECTION_EVENT_FIELDS = (
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
)


@dataclass(frozen=True)
class SelectionEvent:
    schema_version: int
    created_at: str
    workspace_id: str
    scenario_label: str
    scenario_tags: tuple[str, ...]
    selected_pack_ids: tuple[str, ...]
    selected_skill_names: tuple[str, ...]
    manifest_fingerprint: str
    selection_source: str
    outcome: str


def recommendations_dir(runtime_paths: RuntimePaths) -> Path:
    return runtime_paths.state / _RECOMMENDATIONS_DIRNAME


def selection_events_path(runtime_paths: RuntimePaths) -> Path:
    return recommendations_dir(runtime_paths) / _SELECTION_EVENTS_FILENAME


def learned_reference_path(runtime_paths: RuntimePaths) -> Path:
    return recommendations_dir(runtime_paths) / _LEARNED_REFERENCE_FILENAME


def ensure_learned_reference_stub(runtime_paths: RuntimePaths, apply: bool) -> Path:
    path = learned_reference_path(runtime_paths)
    if apply and not path.exists():
        atomic_write_text(path, ASAHINA_EMPTY_REFERENCE)
    return path


def append_selection_event(runtime_paths: RuntimePaths, event: SelectionEvent) -> Path:
    _validate_selection_event(event)
    path = selection_events_path(runtime_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _selection_event_payload(event)
    line = json.dumps(payload, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as file:
        file.write(line)
        file.write("\n")
    return path


def load_selection_events(runtime_paths: RuntimePaths) -> tuple[SelectionEvent, ...]:
    path = selection_events_path(runtime_paths)
    if not path.is_file():
        return ()

    events: list[SelectionEvent] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        event = _selection_event_from_payload(payload)
        if event is not None:
            events.append(event)
    return tuple(events)


def build_learned_reference(events: Iterable[SelectionEvent]) -> str:
    eligible = tuple(
        sorted(
            (event, count)
            for event, count in _count_user_accepted_activation_events(events).items()
            if count >= 10
        )
    )
    if not eligible:
        return ASAHINA_EMPTY_REFERENCE

    lines = ["## Learned Recommendation Hints", ""]
    for event, count in eligible:
        workspace_id, scenario_label, scenario_tags, selected_pack_ids = event
        prefer_recommending = ", ".join(selected_pack_ids)
        lines.extend(
            (
                f"Workspace: {workspace_id}",
                f"Scenario: {scenario_label}",
                f"Scenario tags: {', '.join(scenario_tags)}",
                f"Prefer recommending: {prefer_recommending}",
                f"Evidence: {count} accepted selections",
                "",
            )
        )
    return "\n".join(lines)


def write_learned_reference(runtime_paths: RuntimePaths, reference: str, apply: bool) -> Path:
    path = learned_reference_path(runtime_paths)
    if apply:
        atomic_write_text(path, reference)
    return path


def workspace_id_for_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    digest = hashlib.sha256(resolved.as_posix().encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _selection_event_payload(event: SelectionEvent) -> dict[str, Any]:
    payload = asdict(event)
    payload["scenario_tags"] = list(event.scenario_tags)
    payload["selected_pack_ids"] = list(event.selected_pack_ids)
    payload["selected_skill_names"] = list(event.selected_skill_names)
    return {field: payload[field] for field in _SELECTION_EVENT_FIELDS}


def _selection_event_from_payload(payload: Any) -> SelectionEvent | None:
    if not isinstance(payload, dict):
        return None
    if set(payload) != set(_SELECTION_EVENT_FIELDS):
        return None

    schema_version = payload.get("schema_version")
    created_at = payload.get("created_at")
    workspace_id = payload.get("workspace_id")
    scenario_label = payload.get("scenario_label")
    scenario_tags = _tuple_of_strings(payload.get("scenario_tags"))
    selected_pack_ids = _tuple_of_strings(payload.get("selected_pack_ids"))
    selected_skill_names = _tuple_of_strings(payload.get("selected_skill_names"))
    manifest_fingerprint = payload.get("manifest_fingerprint")
    selection_source = payload.get("selection_source")
    outcome = payload.get("outcome")

    if schema_version != 1:
        return None
    if not all(
        isinstance(value, str)
        for value in (
            created_at,
            workspace_id,
            scenario_label,
            manifest_fingerprint,
            selection_source,
            outcome,
        )
    ):
        return None
    if scenario_tags is None or selected_pack_ids is None or selected_skill_names is None:
        return None

    event = SelectionEvent(
        schema_version=schema_version,
        created_at=created_at,
        workspace_id=workspace_id,
        scenario_label=scenario_label,
        scenario_tags=scenario_tags,
        selected_pack_ids=selected_pack_ids,
        selected_skill_names=selected_skill_names,
        manifest_fingerprint=manifest_fingerprint,
        selection_source=selection_source,
        outcome=outcome,
    )
    try:
        _validate_selection_event(event)
    except ValueError:
        return None
    return event


def _tuple_of_strings(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _count_user_accepted_activation_events(
    events: Iterable[SelectionEvent],
) -> dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], int]:
    counts: dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], int] = {}
    for event in events:
        if event.selection_source != "user_accepted" or event.outcome != "activated":
            continue
        key = (
            event.workspace_id,
            event.scenario_label,
            tuple(sorted(set(event.scenario_tags))),
            event.selected_pack_ids,
        )
        counts[key] = counts.get(key, 0) + 1
    return counts


def _validate_selection_event(event: SelectionEvent) -> None:
    _validate_freeform_label(event.created_at, "created_at", max_length=64)
    _validate_identifier_like(event.workspace_id, "workspace_id")
    _validate_identifier_values(event.scenario_tags, "scenario_tag")
    _validate_scenario_label(event.scenario_label, event.scenario_tags)
    _validate_identifier_values(event.selected_pack_ids, "selected_pack_id")
    _validate_identifier_values(event.selected_skill_names, "selected_skill_name")
    _validate_identifier_like(event.manifest_fingerprint, "manifest_fingerprint")
    _validate_identifier_values((event.selection_source,), "selection_source")
    _validate_identifier_values((event.outcome,), "outcome")


def _validate_scenario_label(value: str, scenario_tags: tuple[str, ...]) -> None:
    _validate_freeform_label(
        value,
        "scenario_label",
        max_length=_MAX_SCENARIO_LABEL_LENGTH,
    )
    canonical_label = " ".join(dict.fromkeys(scenario_tags))
    if value.strip() != canonical_label:
        raise ValueError(f"unsafe scenario_label: {value}")


def _validate_identifier_values(values: tuple[str, ...], label: str) -> None:
    if not values:
        raise ValueError(f"unsafe {label}: empty")
    for value in values:
        if not _SAFE_IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"unsafe {label}: {value}")


def _validate_identifier_like(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"unsafe {label}: empty")
    if _contains_control_characters(value) or _looks_like_path(value):
        raise ValueError(f"unsafe {label}: {value}")


def _validate_freeform_label(value: str, label: str, *, max_length: int) -> None:
    stripped = value.strip()
    if not stripped or len(stripped) > max_length:
        raise ValueError(f"unsafe {label}: {value}")
    if _contains_control_characters(stripped) or _looks_like_path(stripped):
        raise ValueError(f"unsafe {label}: {value}")


def _contains_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _looks_like_path(value: str) -> bool:
    if "/" in value or "\\" in value:
        return True
    return len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] in {"\\", "/"}

