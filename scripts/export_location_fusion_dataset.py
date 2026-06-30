"""Export location-fusion dataset samples from a Message Hub test-run export.

This is an offline DATA-001 helper. It reads an existing
`/api/v1/test-runs/{test_run_id}/export` JSON file, rebuilds observation
windows, and writes `samples.jsonl` plus `manifest.json`.

It does not contact the VPS, read serial ports, flash firmware, or train a
model.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "location_fusion_datasets"
CONTRACT_VERSION = "0.1.0"
GENERATOR_NAME = "export_location_fusion_dataset"
GENERATOR_VERSION = "0.1.0-data001"
LOCATION_EVENT_TYPES = {"location_report", "location_observation"}
RAW_PARSE_FAILURE_STATUSES = {"partial", "checksum_failed", "unsupported", "malformed"}


class DatasetExportError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DatasetExportError(f"failed to read input: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetExportError(f"input is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DatasetExportError("test-run export must be a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def timestamp_key(value: object) -> str:
    return str(value or "")


def first_present(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def number_or_none(value: object) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def event_type(message: dict[str, Any]) -> str:
    return str(message.get("event_type") or "")


def message_type(message: dict[str, Any]) -> str:
    return str(message.get("message_type") or "")


def message_cmd_id(message: dict[str, Any]) -> str | None:
    return first_present(message.get("location_request_cmd_id"), message.get("cmd_id"))  # type: ignore[return-value]


def message_frame_id(message: dict[str, Any]) -> str | None:
    raw_frame = as_dict(message.get("raw_frame"))
    frame_id = raw_frame.get("frame_id")
    return str(frame_id) if frame_id not in (None, "") else None


def raw_frame_parse(record: dict[str, Any]) -> dict[str, Any]:
    return as_dict(record.get("parse_result"))


def raw_frame_derived(record: dict[str, Any]) -> dict[str, Any]:
    return as_dict(raw_frame_parse(record).get("derived_message"))


def raw_frame_type(record: dict[str, Any]) -> str | None:
    framing = as_dict(record.get("framing"))
    value = first_present(framing.get("frame_type"), record.get("frame_type"))
    return str(value) if value not in (None, "") else None


def raw_frame_cmd_id(record: dict[str, Any]) -> str | None:
    derived = raw_frame_derived(record)
    value = first_present(derived.get("location_request_cmd_id"), derived.get("cmd_id"))
    if value not in (None, ""):
        return str(value)
    frame_id = str(record.get("frame_id") or "")
    if frame_id.startswith(("loc-", "obs-", "ack-")):
        return frame_id.split("-", 1)[1]
    if frame_id.startswith("cmd-"):
        return frame_id
    return None


def raw_frame_ref(record: dict[str, Any]) -> dict[str, Any]:
    raw_payload = as_dict(record.get("raw_payload"))
    framing = as_dict(record.get("framing"))
    parse = raw_frame_parse(record)
    derived = raw_frame_derived(record)
    retention = as_dict(record.get("retention"))
    return compact_dict(
        {
            "frame_id": str(record.get("frame_id") or ""),
            "direction": record.get("direction"),
            "device_id": first_present(record.get("device_id"), derived.get("device_id")),
            "test_run_id": first_present(record.get("test_run_id"), derived.get("test_run_id")),
            "cmd_id": first_present(
                record.get("cmd_id"),
                derived.get("cmd_id"),
                derived.get("location_request_cmd_id"),
                raw_frame_cmd_id(record),
            ),
            "seq": first_present(record.get("seq"), derived.get("seq")),
            "fw_version": first_present(record.get("fw_version"), derived.get("fw_version")),
            "frame_type": raw_frame_type(record),
            "server_received_at": record.get("server_received_at"),
            "byte_len": raw_payload.get("byte_len"),
            "sha256": raw_payload.get("sha256"),
            "crc32": first_present(raw_payload.get("crc32"), framing.get("payload_crc32")),
            "parse_status": str(parse.get("status") or "unknown"),
            "parser_version": parse.get("parser_version"),
            "derived_message_type": parse.get("derived_message_type"),
            "privacy_class": retention.get("privacy_class"),
            "redacted": bool(raw_payload.get("data_redacted") or "data" not in raw_payload),
        }
    )


def derived_event_ref(message: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "message_type": message.get("message_type"),
            "event_type": message.get("event_type"),
            "cmd_id": message_cmd_id(message),
            "frame_id": message_frame_id(message),
            "seq": message.get("seq"),
            "server_received_at": message.get("server_received_at"),
            "fw_version": message.get("fw_version"),
            "test_run_id": message.get("test_run_id"),
            "source": message.get("source"),
            "source_status": message.get("source_status"),
        }
    )


def sanitize_gnss(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {}
    return compact_dict(
        {
            "fix": report.get("fix"),
            "state": first_present(report.get("gnss_state"), as_dict(report.get("gnss")).get("state")),
            "query_ok": report.get("gnss_query_ok"),
            "source": report.get("source"),
            "source_status": report.get("source_status"),
            "satellites": report.get("satellites"),
            "hdop": report.get("hdop"),
            "lat_present": report.get("lat") is not None,
            "lon_present": report.get("lon") is not None,
            "location_request_cmd_id": report.get("location_request_cmd_id"),
        }
    )


def private_coordinates(report: dict[str, Any], *, include_private_location: bool) -> dict[str, Any]:
    if not include_private_location:
        return {}
    if report.get("lat") is None or report.get("lon") is None:
        return {}
    return {"latitude_deg": report.get("lat"), "longitude_deg": report.get("lon")}


def sanitize_wifi(observation: dict[str, Any]) -> dict[str, Any]:
    wifi = as_dict(observation.get("wifi"))
    if not wifi:
        return {}
    result = {key: value for key, value in wifi.items() if key != "aps"}
    aps: list[dict[str, Any]] = []
    for ap in as_list(wifi.get("aps")):
        ap_dict = as_dict(ap)
        safe_ap = compact_dict({"bssid_hash": ap_dict.get("bssid_hash"), "rssi": ap_dict.get("rssi")})
        if safe_ap:
            aps.append(safe_ap)
    if aps:
        result["aps"] = aps
    return result


def build_features(
    *,
    report: dict[str, Any],
    observation: dict[str, Any],
    command: dict[str, Any],
    raw_refs: list[dict[str, Any]],
    observability_summary: dict[str, Any],
    include_private_location: bool,
) -> dict[str, Any]:
    ack = as_dict(command.get("ack"))
    command_obs = as_dict(ack.get("command"))
    gnss = sanitize_gnss(report)
    gnss.update(private_coordinates(report, include_private_location=include_private_location))
    return {
        "gnss": gnss,
        "cell": as_dict(observation.get("cell")),
        "lte": as_dict(observation.get("lte")),
        "transport": first_non_empty_dict(
            as_dict(observation.get("transport")),
            as_dict(report.get("transport")),
            as_dict(ack.get("transport")),
        ),
        "lte_http": first_non_empty_dict(
            as_dict(observation.get("lte_http")),
            as_dict(report.get("lte_http")),
            as_dict(ack.get("lte_http")),
        ),
        "runtime": first_non_empty_dict(as_dict(observation.get("runtime")), as_dict(report.get("runtime"))),
        "wifi": sanitize_wifi(observation),
        "imu": as_dict(observation.get("imu")),
        "power": as_dict(observation.get("power")),
        "location_belief": as_dict(observation.get("location_belief")),
        "command": compact_dict(
            {
                "cmd_id": command.get("cmd_id"),
                "cmd": command.get("cmd"),
                "status": command.get("status"),
                "ack_status": ack.get("status"),
                "duplicate_local_execution_prevented": command_obs.get("duplicate_local_execution_prevented"),
                "command_count": command_obs.get("command_count"),
            }
        ),
        "raw_frame_statuses": [ref.get("parse_status") for ref in raw_refs],
        "observability": as_dict(observability_summary.get("latest_observability")),
    }


def first_non_empty_dict(*values: dict[str, Any]) -> dict[str, Any]:
    for value in values:
        if value:
            return value
    return {}


def location_state_and_source(report: dict[str, Any], observation: dict[str, Any]) -> tuple[str, str, float | None]:
    belief = as_dict(observation.get("location_belief"))
    state = belief.get("state")
    if state in {"Fine", "Coarse", "Predicted", "Unknown"}:
        confidence = number_or_none(belief.get("confidence"))
        return str(state), "location_belief", confidence
    if report.get("fix") is True:
        return "Fine", "gnss_report", 1.0
    return "Unknown", "rule", None


def failure_modes(
    *,
    report: dict[str, Any],
    observation: dict[str, Any],
    command: dict[str, Any],
    raw_refs: list[dict[str, Any]],
    expect_location_report: bool,
    expect_location_observation: bool,
) -> list[str]:
    modes: set[str] = set()
    if report.get("fix") is False:
        modes.add("gnss_no_fix")
    if expect_location_report and not report:
        modes.add("missing_location_report")
    if expect_location_observation and not observation:
        modes.add("missing_location_observation")
    if command:
        if command.get("status") != "ok":
            modes.add("missing_ack")
        ack = as_dict(command.get("ack"))
        if as_dict(ack.get("transport")).get("type") not in (None, "", "lte"):
            modes.add("transport_not_lte")
    for ref in raw_refs:
        status = str(ref.get("parse_status") or "")
        if status in RAW_PARSE_FAILURE_STATUSES:
            modes.add("raw_parse_failed")
        if status == "checksum_failed":
            modes.add("checksum_failed")
    return sorted(modes)


def privacy_block(
    *,
    report: dict[str, Any],
    raw_refs: list[dict[str, Any]],
    allow_private_location_training: bool,
) -> dict[str, Any]:
    has_private_location = report.get("lat") is not None or report.get("lon") is not None
    privacy_class = "private_location" if has_private_location else "engineering"
    redacted = all(ref.get("redacted", True) for ref in raw_refs)
    exclusion_reasons: list[str] = []
    training_allowed = True
    if has_private_location and not allow_private_location_training:
        training_allowed = False
        exclusion_reasons.append("private_location_training_not_explicitly_allowed")
    return {
        "privacy_class": privacy_class,
        "redacted": redacted,
        "collection_allowed": True,
        "training_allowed": training_allowed,
        "raw_audio_allowed": False,
        "raw_image_allowed": False,
        "exclusion_reasons": exclusion_reasons,
    }


def quality_block(
    *,
    messages: list[dict[str, Any]],
    raw_refs: list[dict[str, Any]],
    command: dict[str, Any],
    privacy: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    if not raw_refs:
        warnings.append("missing_raw_frame_lineage")
    if not all(message.get("server_received_at") for message in messages):
        warnings.append("missing_server_received_at")
    if has_sequence_regression(messages):
        warnings.append("sequence_regression")
    ack = as_dict(command.get("ack"))
    command_obs = as_dict(ack.get("command"))
    command_count = command_obs.get("command_count")
    duplicate_prevented = bool_value(command_obs.get("duplicate_local_execution_prevented"))
    if isinstance(command_count, int) and command_count > 1 and duplicate_prevented is not True:
        warnings.append("duplicate_command_execution_risk")
    if command and command.get("status") == "pending":
        warnings.append("stale_or_pending_command")
    if not privacy.get("training_allowed"):
        warnings.append("training_not_allowed_by_privacy_policy")
    if any(ref.get("parse_status") in RAW_PARSE_FAILURE_STATUSES for ref in raw_refs):
        warnings.append("raw_frame_parse_failure")
    status = "fail" if errors else ("warn" if warnings else "pass")
    return {"status": status, "warnings": sorted(set(warnings)), "errors": errors}


def has_sequence_regression(messages: list[dict[str, Any]]) -> bool:
    seqs: list[int] = []
    for message in sorted(messages, key=lambda item: timestamp_key(item.get("server_received_at"))):
        seq = message.get("seq")
        if isinstance(seq, int):
            seqs.append(seq)
    return any(current < previous for previous, current in zip(seqs, seqs[1:]))


def window_times(items: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    times = sorted(str(item.get("server_received_at") or item.get("created_at") or "") for item in items)
    times = [value for value in times if value]
    if not times:
        return None, None
    return times[0], times[-1]


def make_sample(
    *,
    sample_id: str,
    sample_type: str,
    test_run_id: str,
    device_id: str,
    command: dict[str, Any],
    report: dict[str, Any],
    observation: dict[str, Any],
    events: list[dict[str, Any]],
    raw_records: list[dict[str, Any]],
    observability_summary: dict[str, Any],
    split_name: str,
    split_rule: str,
    include_private_location: bool,
    allow_private_location_training: bool,
    created_at: str,
) -> dict[str, Any]:
    raw_refs = [raw_frame_ref(record) for record in raw_records]
    privacy = privacy_block(
        report=report,
        raw_refs=raw_refs,
        allow_private_location_training=allow_private_location_training,
    )
    quality = quality_block(messages=events, raw_refs=raw_refs, command=command, privacy=privacy)
    state, label_source, confidence = location_state_and_source(report, observation)
    modes = failure_modes(
        report=report,
        observation=observation,
        command=command,
        raw_refs=raw_refs,
        expect_location_report=bool(command and command.get("cmd") == "request_location"),
        expect_location_observation=bool(command and command.get("cmd") == "request_location"),
    )
    if modes and sample_type != "known_place_calibration_window":
        sample_type = "failure_window"
    start_at, end_at = window_times([*events, command, as_dict(command.get("ack"))])
    anchor_event = first_present(message_frame_id(observation), message_frame_id(report))
    if anchor_event is None and events:
        anchor_event = f"{event_type(events[0])}:seq-{events[0].get('seq')}"
    return {
        "contract_version": CONTRACT_VERSION,
        "sample_id": sample_id,
        "sample_type": sample_type,
        "device_id": device_id,
        "test_run_id": test_run_id,
        "window": {
            "start_server_received_at": start_at,
            "end_server_received_at": end_at,
            "anchor_event_id": anchor_event,
            "anchor_cmd_id": command.get("cmd_id"),
        },
        "lineage": {
            "raw_frame_refs": raw_refs,
            "derived_event_refs": [derived_event_ref(event) for event in events],
        },
        "features": build_features(
            report=report,
            observation=observation,
            command=command,
            raw_refs=raw_refs,
            observability_summary=observability_summary,
            include_private_location=include_private_location,
        ),
        "labels": {
            "location_state": state,
            "label_source": label_source,
            "confidence": confidence,
            "failure_modes": modes,
        },
        "quality": quality,
        "privacy": privacy,
        "split": {"name": split_name, "rule": split_rule},
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "created_at": created_at},
    }


def command_matches_location(command: dict[str, Any], events: list[dict[str, Any]], raw_records: list[dict[str, Any]]) -> bool:
    if command.get("cmd") == "request_location":
        return True
    cmd_id = str(command.get("cmd_id") or "")
    if not cmd_id:
        return False
    return any(message_cmd_id(event) == cmd_id for event in events) or any(raw_frame_cmd_id(record) == cmd_id for record in raw_records)


def raw_records_for_command(raw_records: list[dict[str, Any]], cmd_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_frame_ids = {message_frame_id(event) for event in events if message_frame_id(event)}
    matched: list[dict[str, Any]] = []
    for record in raw_records:
        frame_id = str(record.get("frame_id") or "")
        if raw_frame_cmd_id(record) == cmd_id or frame_id in event_frame_ids or cmd_id in frame_id:
            matched.append(record)
    return dedupe_raw_records(matched)


def dedupe_raw_records(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in raw_records:
        key = str(first_present(record.get("frame_id"), record.get("server_received_at"), id(record)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def build_dataset(
    export: dict[str, Any],
    *,
    split_name: str = "unassigned",
    split_rule: str = "manual_unassigned_no_leakage_check",
    include_private_location: bool = False,
    allow_private_location_training: bool = False,
    created_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    created_at = created_at or utc_now()
    test_run = as_dict(export.get("test_run"))
    test_run_id = str(first_present(test_run.get("test_run_id"), export.get("test_run_id"), "unknown-test-run"))
    messages = [item for item in as_list(export.get("messages")) if isinstance(item, dict)]
    commands = [item for item in as_list(export.get("commands")) if isinstance(item, dict)]
    raw_records = [item for item in as_list(export.get("raw_frames")) if isinstance(item, dict)]
    observability_summary = as_dict(export.get("observability_summary"))
    location_events = [
        message
        for message in messages
        if message_type(message) == "event" and event_type(message) in LOCATION_EVENT_TYPES
    ]

    samples: list[dict[str, Any]] = []
    covered_event_ids: set[int] = set()
    covered_raw_frame_ids: set[str] = set()

    for command in commands:
        if not command_matches_location(command, location_events, raw_records):
            continue
        cmd_id = str(command.get("cmd_id") or "")
        events = [event for event in location_events if message_cmd_id(event) == cmd_id]
        report = next((event for event in events if event_type(event) == "location_report"), {})
        observation = next((event for event in events if event_type(event) == "location_observation"), {})
        relevant_raw = raw_records_for_command(raw_records, cmd_id, events)
        sample_id = f"{test_run_id}:{cmd_id or 'command'}:location"
        sample_type = "location_request_window"
        if report.get("fix") is True:
            sample_type = "known_place_calibration_window"
        sample = make_sample(
            sample_id=sample_id,
            sample_type=sample_type,
            test_run_id=test_run_id,
            device_id=str(first_present(command.get("device_id"), report.get("device_id"), observation.get("device_id"), "unknown")),
            command=command,
            report=report,
            observation=observation,
            events=events,
            raw_records=relevant_raw,
            observability_summary=observability_summary,
            split_name=split_name,
            split_rule=split_rule,
            include_private_location=include_private_location,
            allow_private_location_training=allow_private_location_training,
            created_at=created_at,
        )
        samples.append(sample)
        covered_event_ids.update(id(event) for event in events)
        covered_raw_frame_ids.update(str(record.get("frame_id") or "") for record in relevant_raw)

    for event in location_events:
        if id(event) in covered_event_ids:
            continue
        frame_id = message_frame_id(event)
        relevant_raw = [record for record in raw_records if str(record.get("frame_id") or "") == frame_id]
        report = event if event_type(event) == "location_report" else {}
        observation = event if event_type(event) == "location_observation" else {}
        sample_id = f"{test_run_id}:{event_type(event)}:seq-{event.get('seq', 'unknown')}"
        sample = make_sample(
            sample_id=sample_id,
            sample_type="passive_observation_window",
            test_run_id=test_run_id,
            device_id=str(first_present(event.get("device_id"), "unknown")),
            command={},
            report=report,
            observation=observation,
            events=[event],
            raw_records=relevant_raw,
            observability_summary=observability_summary,
            split_name=split_name,
            split_rule=split_rule,
            include_private_location=include_private_location,
            allow_private_location_training=allow_private_location_training,
            created_at=created_at,
        )
        samples.append(sample)
        covered_raw_frame_ids.update(str(record.get("frame_id") or "") for record in relevant_raw)

    for record in raw_records:
        frame_id = str(record.get("frame_id") or "")
        parse_status = str(raw_frame_parse(record).get("status") or "")
        if frame_id in covered_raw_frame_ids or parse_status not in RAW_PARSE_FAILURE_STATUSES:
            continue
        sample_id = f"{test_run_id}:raw-frame:{frame_id or len(samples)}"
        sample = make_sample(
            sample_id=sample_id,
            sample_type="failure_window",
            test_run_id=test_run_id,
            device_id=str(first_present(record.get("device_id"), "unknown")),
            command={},
            report={},
            observation={},
            events=[],
            raw_records=[record],
            observability_summary=observability_summary,
            split_name=split_name,
            split_rule=split_rule,
            include_private_location=include_private_location,
            allow_private_location_training=allow_private_location_training,
            created_at=created_at,
        )
        samples.append(sample)

    manifest = build_manifest(
        test_run_id=test_run_id,
        test_run=test_run,
        samples=samples,
        messages=messages,
        commands=commands,
        raw_records=raw_records,
        created_at=created_at,
        split_name=split_name,
        split_rule=split_rule,
    )
    return samples, manifest


def build_manifest(
    *,
    test_run_id: str,
    test_run: dict[str, Any],
    samples: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    raw_records: list[dict[str, Any]],
    created_at: str,
    split_name: str,
    split_rule: str,
) -> dict[str, Any]:
    failure_counts = Counter()
    privacy_counts = Counter()
    quality_counts = Counter()
    sample_type_counts = Counter()
    for sample in samples:
        sample_type_counts[sample["sample_type"]] += 1
        quality_counts[sample["quality"]["status"]] += 1
        privacy_counts[sample["privacy"]["privacy_class"]] += 1
        failure_counts.update(sample["labels"]["failure_modes"])
    return {
        "contract_version": CONTRACT_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "created_at": created_at},
        "source": {
            "test_run_id": test_run_id,
            "test_run": test_run,
            "message_count": len(messages),
            "command_count": len(commands),
            "raw_frame_count": len(raw_records),
        },
        "schema": {
            "sample_schema": "shared/contracts/location_fusion_sample.schema.json",
            "raw_frame_schema": "shared/contracts/message_hub_raw_frame_record.schema.json",
            "event_schema": "shared/contracts/message_hub_event.schema.json",
        },
        "outputs": {"samples_jsonl": "samples.jsonl", "manifest_json": "manifest.json"},
        "counts": {
            "samples": len(samples),
            "sample_types": dict(sorted(sample_type_counts.items())),
            "quality": dict(sorted(quality_counts.items())),
            "privacy": dict(sorted(privacy_counts.items())),
            "failure_modes": dict(sorted(failure_counts.items())),
        },
        "split": {
            "name": split_name,
            "rule": split_rule,
            "leakage_check": {
                "status": "single_export_not_split",
                "note": "Do not mix rows from the same field session across train and test.",
            },
        },
        "privacy": {
            "raw_payload_policy": "raw frame payload bytes are not copied into dataset samples",
            "raw_audio_allowed": False,
            "raw_image_allowed": False,
        },
    }


def export_dataset(
    input_path: Path,
    output_dir: Path,
    *,
    split_name: str,
    split_rule: str,
    include_private_location: bool,
    allow_private_location_training: bool,
) -> dict[str, Any]:
    export = load_json(input_path)
    samples, manifest = build_dataset(
        export,
        split_name=split_name,
        split_rule=split_rule,
        include_private_location=include_private_location,
        allow_private_location_training=allow_private_location_training,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "samples.jsonl"
    manifest_path = output_dir / "manifest.json"
    write_jsonl(samples_path, samples)
    write_json(manifest_path, manifest)
    return {"samples": samples, "manifest": manifest, "samples_path": str(samples_path), "manifest_path": str(manifest_path)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "--test-run-export", dest="input_path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--split",
        choices=["train", "validation", "test", "holdout", "unassigned"],
        default="unassigned",
    )
    parser.add_argument("--split-rule", default="manual_unassigned_no_leakage_check")
    parser.add_argument("--include-private-location", action="store_true")
    parser.add_argument("--allow-private-location-training", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.allow_private_location_training and not args.include_private_location:
        print(
            "FAIL location fusion dataset export: --allow-private-location-training requires --include-private-location",
            file=sys.stderr,
        )
        return 1
    try:
        export = load_json(args.input_path)
        test_run = as_dict(export.get("test_run"))
        test_run_id = str(first_present(test_run.get("test_run_id"), export.get("test_run_id"), "unknown-test-run"))
        output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / test_run_id
        result = export_dataset(
            args.input_path,
            output_dir,
            split_name=args.split,
            split_rule=args.split_rule,
            include_private_location=args.include_private_location,
            allow_private_location_training=args.allow_private_location_training,
        )
    except DatasetExportError as exc:
        print(f"FAIL location fusion dataset export: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result["manifest"], ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "PASS location fusion dataset export "
            f"samples={result['manifest']['counts']['samples']} output={result['manifest_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
