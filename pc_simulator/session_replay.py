"""Replay Ego Link M1 session recordings through the Safety Companion M0."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from pc_simulator import safety_companion, session_annotations, session_inspector


REPLAY_SCHEMA_VERSION = "egolink.session_replay_report.v0.1"
UPTIME_RE = re.compile(r"^uptime_ms:(?P<value>\d+)$")
DERIVED_EVENT_TYPES = {"safety_evaluation", "safety_event", "command_sent"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    if UPTIME_RE.match(text):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def monotonic_ms(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    match = UPTIME_RE.match(value)
    if match is None:
        return None
    return int(match.group("value"))


def int_or_none(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float_value(value, 0.0)


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def replay_recording(
    recording_dir: Path,
    *,
    generated_at: str | None = None,
    require_quality: bool = True,
) -> dict[str, Any]:
    recording_dir = recording_dir.resolve()
    generated = generated_at or utc_now()
    quality_report = session_inspector.inspect_recording(recording_dir, generated_at=generated)

    if require_quality and not quality_report["passed"]:
        return quality_failure_report(recording_dir, quality_report, generated_at=generated)

    manifest = load_json(recording_dir / "session_manifest.json")
    sensor_frames = load_jsonl(recording_dir / "sensor_frames.jsonl")
    events = load_jsonl(recording_dir / "events.jsonl")
    annotations = load_jsonl(recording_dir / "annotations.jsonl")
    timeline = build_timeline(sensor_frames, events)

    state = initial_replay_state(manifest)
    records: list[dict[str, Any]] = []
    for index, item in enumerate(timeline, start=1):
        update_state_from_record(state, item)
        records.append(replay_timeline_record(item, manifest, state, index))

    return build_report(
        recording_dir=recording_dir,
        generated_at=generated,
        manifest=manifest,
        quality_report=quality_report,
        annotations=annotations,
        records=records,
    )


def quality_failure_report(
    recording_dir: Path,
    quality_report: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "generated_at": generated_at,
        "recording_dir": str(recording_dir),
        "session_id": None,
        "passed": False,
        "quality_gate": {
            "passed": False,
            "quality_score": quality_report["quality_score"],
            "errors": quality_report["summary"]["errors"],
            "warnings": quality_report["summary"]["warnings"],
        },
        "summary": empty_summary(),
        "errors": [
            {
                "code": "quality_gate_failed",
                "message": "Recording failed quality gate; replay was not executed.",
            }
        ],
        "quality_errors": quality_report["errors"],
        "quality_warnings": quality_report["warnings"],
        "records": [],
    }


def empty_summary() -> dict[str, Any]:
    return {
        "timeline_records": 0,
        "sensor_frames": 0,
        "events": 0,
        "replayed_inputs": 0,
        "skipped_records": 0,
        "model_outputs": 0,
        "safety_events": 0,
        "base_commands": 0,
        "risk_types": {},
        "recommended_actions": {},
        "annotations": 0,
        "annotation_labels": {},
        "annotation_outcomes": {},
        "annotator_types": {},
    }


def build_timeline(sensor_frames: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(sensor_frames, start=1):
        item = deepcopy(row)
        item["_source_file"] = "sensor_frames"
        item["_file_index"] = index
        rows.append(item)
    for index, row in enumerate(events, start=1):
        item = deepcopy(row)
        item["_source_file"] = "events"
        item["_file_index"] = index
        rows.append(item)
    return sorted(rows, key=timeline_sort_key)


def timeline_sort_key(row: Mapping[str, Any]) -> tuple[int, int, int, int]:
    seq = int_or_none(row.get("seq"))
    if seq is not None:
        primary = (0, seq)
    else:
        time_value = timestamp_ms(row.get("received_at") or row.get("ts"))
        if time_value is not None:
            primary = (1, time_value)
        else:
            mono = int_or_none(row.get("monotonic_ms")) or monotonic_ms(row.get("ts"))
            primary = (2, mono if mono is not None else int(row.get("_file_index", 0)))
    source_rank = 0 if row.get("_source_file") == "sensor_frames" else 1
    return primary[0], primary[1], source_rank, int(row.get("_file_index", 0))


def initial_replay_state(manifest: Mapping[str, Any]) -> dict[str, Any]:
    privacy = manifest.get("privacy") if isinstance(manifest.get("privacy"), dict) else {}
    structured_only = privacy.get("mode") == "structured_only"
    return {
        "device_id": first_device_id(manifest),
        "mode": "personal_safety",
        "battery": 100.0,
        "charging": False,
        "rssi": None,
        "link_type": "unknown",
        "online": True,
        "privacy_mode": bool(structured_only),
        "camera_available": bool(privacy.get("raw_image_allowed", False)),
        "microphone_available": bool(privacy.get("raw_audio_allowed", False)),
        "location": None,
    }


def first_device_id(manifest: Mapping[str, Any]) -> str:
    device_ids = manifest.get("device_ids")
    if isinstance(device_ids, list) and device_ids:
        return str(device_ids[0])
    return "ego-link-001"


def update_state_from_record(state: dict[str, Any], row: Mapping[str, Any]) -> None:
    for key in ("device_id", "link_type", "guard_mode"):
        if row.get(key) not in (None, ""):
            target = "mode" if key == "guard_mode" else key
            state[target] = row[key]
    if row.get("battery") not in (None, ""):
        state["battery"] = float_value(row.get("battery"), float_value(state.get("battery"), 100.0))
    if row.get("charging") is not None:
        state["charging"] = bool_value(row.get("charging"), bool_value(state.get("charging"), False))
    rssi = row.get("wifi_rssi") if row.get("wifi_rssi") is not None else row.get("rssi")
    if rssi is not None:
        state["rssi"] = int_or_none(rssi)
    if row.get("frame_type") == "gnss_report":
        state["location"] = dict(row)


def replay_timeline_record(
    row: Mapping[str, Any],
    manifest: Mapping[str, Any],
    state: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    result = {
        "index": index,
        "source_file": row.get("_source_file"),
        "source_event_key": row.get("source_event_key"),
        "source_event_type": row.get("source_event_type"),
        "record_type": row.get("record_type"),
        "frame_type": row.get("frame_type"),
        "event_type": row.get("event_type"),
        "seq": row.get("seq"),
        "ts": row.get("ts"),
        "replayed": False,
    }

    skip_reason = skip_reason_for_record(row)
    if skip_reason is not None:
        result["skip_reason"] = skip_reason
        return result

    sensor_frame = build_replay_sensor_frame(row, manifest, state, index)
    bundle = safety_companion.evaluate_sensor_frame_bundle(sensor_frame)
    result.update(
        {
            "replayed": True,
            "sensor_frame": bundle["sensor_frame"],
            "model_input": bundle["model_input"],
            "model_output": bundle["model_output"],
            "safety_event": bundle["safety_event"],
            "base_command": bundle["base_command"],
        }
    )
    return result


def skip_reason_for_record(row: Mapping[str, Any]) -> str | None:
    if row.get("record_type") == "sensor_frame":
        return None
    event_type = str(row.get("event_type") or "")
    if event_type in DERIVED_EVENT_TYPES:
        return "derived_record"
    if event_type and safety_companion.is_evaluable_event(row):
        return None
    return "not_model_evaluable"


def build_replay_sensor_frame(
    row: Mapping[str, Any],
    manifest: Mapping[str, Any],
    state: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    timestamp = record_timestamp_ms(row, manifest, index)
    source_event_key = str(row.get("source_event_key") or f"row-{index}")
    frame_id = f"replay-{index:04d}-{short_hash(source_event_key)}"
    sequence = int_or_none(row.get("seq"))
    if sequence is None:
        sequence = index

    return {
        "contract_version": safety_companion.CONTRACT_VERSION,
        "frame_id": frame_id,
        "device_id": str(row.get("device_id") or state.get("device_id") or first_device_id(manifest)),
        "timestamp_ms": timestamp,
        "monotonic_ms": int_or_none(row.get("monotonic_ms")) or monotonic_ms(row.get("ts")),
        "sequence": max(0, int(sequence)),
        "mode": normalized_mode(str(state.get("mode") or "personal_safety")),
        "source": "replay",
        "sensors": {
            "motion": build_motion_sensor(row),
            "audio": build_audio_sensor(row),
            "location": build_location_sensor(row, state),
            "network": build_network_sensor(row, state),
            "device": build_device_sensor(row, state),
            "user_input": build_user_input_sensor(row),
        },
        "metadata": {
            "recording_session_id": manifest.get("session_id"),
            "source_event_key": source_event_key,
            "source_event_type": row.get("source_event_type"),
            "record_type": row.get("record_type"),
            "frame_type": row.get("frame_type"),
            "event_type": row.get("event_type"),
            "source_file": row.get("_source_file"),
            "file_index": row.get("_file_index"),
        },
    }


def record_timestamp_ms(row: Mapping[str, Any], manifest: Mapping[str, Any], index: int) -> int:
    direct = timestamp_ms(row.get("received_at") or row.get("ts"))
    if direct is not None:
        return direct
    created = timestamp_ms(manifest.get("created_at")) or 0
    mono = int_or_none(row.get("monotonic_ms")) or monotonic_ms(row.get("ts"))
    if created and mono is not None:
        return created + max(0, mono)
    return created + index if created else index


def normalized_mode(value: str) -> str:
    if value in {"personal_safety", "child_safety", "elder_safety", "cycling", "test"}:
        return value
    return "personal_safety"


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def build_motion_sensor(row: Mapping[str, Any]) -> dict[str, Any] | None:
    event_type = str(row.get("event_type") or "")
    if event_type not in {"impact_detected", "post_impact_inactivity", "possible_fall"}:
        return None
    impact_score = 0.92 if event_type in {"impact_detected", "post_impact_inactivity"} else 0.0
    fall_score = 0.91 if event_type == "possible_fall" else 0.0
    return {
        "sample_rate_hz": 50.0,
        "window_duration_ms": 2560,
        "accel_mps2": None,
        "gyro_rad_s": None,
        "summary": {
            "activity_label": "fall_candidate" if event_type == "possible_fall" else "impact",
            "activity_confidence": 0.9,
            "max_accel_g": 1.2,
            "jerk_peak_g_s": 2.0,
            "orientation_change_deg": 0.0,
            "impact_score": impact_score,
            "fall_score": fall_score,
            "stationary_seconds": 20.0 if event_type == "post_impact_inactivity" else 0.0,
            "device_worn": True,
        },
        "raw_ref": None,
    }


def build_audio_sensor(row: Mapping[str, Any]) -> dict[str, Any] | None:
    event_type = str(row.get("event_type") or "")
    if event_type != "wake_detected":
        return None
    confidence = clamp_float(float_value(row.get("confidence"), 0.0), 0.0, 1.0)
    return {
        "sample_rate_hz": 16000,
        "window_duration_ms": 1000,
        "vad_probability": confidence,
        "rms_dbfs": -48.0,
        "peak_dbfs": -31.0,
        "quality_score": 0.9,
        "event_scores": {
            "speech": confidence,
            "distress": 0.0,
            "impact": 0.0,
            "unknown_loud_sound": 0.0,
        },
        "clip_ref": None,
    }


def build_location_sensor(row: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any] | None:
    source = row if row.get("frame_type") == "gnss_report" else state.get("location")
    if not isinstance(source, Mapping):
        return None
    fix_valid = bool_value(source.get("fix"), False)
    return {
        "fix_valid": fix_valid,
        "latitude_deg": optional_float(source.get("lat")),
        "longitude_deg": optional_float(source.get("lon")),
        "speed_mps": max(0.0, float_value(source.get("speed_mps"), 0.0)),
        "heading_deg": optional_float(source.get("heading_deg")),
        "accuracy_m": optional_float(source.get("accuracy_m")),
        "fix_age_ms": int_or_none(source.get("fix_age_ms")) if fix_valid else None,
        "outside_safe_zone": bool_value(source.get("outside_safe_zone"), False),
        "dwell_seconds": max(0.0, float_value(source.get("dwell_seconds"), 0.0)),
        "route_deviation_m": max(0.0, float_value(source.get("route_deviation_m"), 0.0)),
        "quality_score": 0.85 if fix_valid else 0.0,
    }


def build_network_sensor(row: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    rssi = row.get("wifi_rssi") if row.get("wifi_rssi") is not None else row.get("rssi")
    if rssi is None:
        rssi = state.get("rssi")
    rssi_value = int_or_none(rssi)
    registered = bool_value(state.get("online"), True)
    link_type = safety_companion.link_type_from_device({"link_type": state.get("link_type")})
    return {
        "registered": registered,
        "link_type": link_type,
        "rssi_dbm": rssi_value if rssi_value is not None and rssi_value > -160 else None,
        "signal_level": safety_companion.signal_level(rssi_value if rssi_value is not None else -120),
        "round_trip_ms": None,
        "upload_available": registered,
        "base_online": registered,
        "offline_seconds": 0.0 if registered else 1200.0,
    }


def build_device_sensor(row: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    battery = row.get("battery") if row.get("battery") is not None else state.get("battery")
    charging = row.get("charging") if row.get("charging") is not None else state.get("charging")
    return {
        "battery_percent": clamp_float(float_value(battery, 100.0), 0.0, 100.0),
        "charging": bool_value(charging, False),
        "temperature_c": optional_float(row.get("temperature_c")),
        "privacy_mode": bool_value(state.get("privacy_mode"), False),
        "camera_available": bool_value(state.get("camera_available"), False),
        "microphone_available": bool_value(state.get("microphone_available"), False),
    }


def build_user_input_sensor(row: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(row.get("event_type") or "")
    return {
        "sos_pressed": event_type in {"sos_pressed", "manual_sos"} or bool_value(row.get("sos_pressed"), False),
        "cancel_pressed": bool_value(row.get("cancel_pressed"), False),
        "response": str(row.get("response") or "none"),
    }


def build_report(
    *,
    recording_dir: Path,
    generated_at: str,
    manifest: Mapping[str, Any],
    quality_report: dict[str, Any],
    annotations: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    replayed = [record for record in records if record.get("replayed")]
    model_outputs = [record["model_output"] for record in replayed]
    annotation_summary = session_annotations.summarize_annotations(annotations)
    summary = {
        "timeline_records": len(records),
        "sensor_frames": sum(1 for record in records if record.get("source_file") == "sensor_frames"),
        "events": sum(1 for record in records if record.get("source_file") == "events"),
        "annotations": len(annotations),
        "replayed_inputs": len(replayed),
        "skipped_records": sum(1 for record in records if not record.get("replayed")),
        "model_outputs": len(model_outputs),
        "safety_events": sum(1 for record in replayed if record.get("safety_event") is not None),
        "base_commands": sum(1 for record in replayed if record.get("base_command") is not None),
        "risk_types": dict(sorted(Counter(output["risk_type"] for output in model_outputs).items())),
        "recommended_actions": dict(sorted(Counter(output["recommended_action"] for output in model_outputs).items())),
        **annotation_summary,
    }
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "generated_at": generated_at,
        "recording_dir": str(recording_dir),
        "session_id": manifest.get("session_id"),
        "passed": quality_report["passed"],
        "quality_gate": {
            "passed": quality_report["passed"],
            "quality_score": quality_report["quality_score"],
            "errors": quality_report["summary"]["errors"],
            "warnings": quality_report["summary"]["warnings"],
        },
        "summary": summary,
        "errors": [],
        "quality_errors": quality_report["errors"],
        "quality_warnings": quality_report["warnings"],
        "records": records,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Ego Link Session Replay Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Recording dir: `{report['recording_dir']}`",
        f"- Session ID: `{report.get('session_id')}`",
        f"- Passed: `{report['passed']}`",
        f"- Quality gate: `{report['quality_gate']['passed']}` score `{report['quality_gate']['quality_score']}`",
        f"- Timeline records: `{summary['timeline_records']}`",
        f"- Replayed inputs: `{summary['replayed_inputs']}`",
        f"- Skipped records: `{summary['skipped_records']}`",
        f"- Annotations: `{summary.get('annotations', 0)}`",
        f"- Safety events: `{summary['safety_events']}`",
        f"- Base commands: `{summary['base_commands']}`",
        "",
        "## Risk Types",
        "",
    ]
    if summary.get("risk_types"):
        for risk_type, count in summary["risk_types"].items():
            lines.append(f"- `{risk_type}`: `{count}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Recommended Actions", ""])
    if summary.get("recommended_actions"):
        for action, count in summary["recommended_actions"].items():
            lines.append(f"- `{action}`: `{count}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Annotation Labels", ""])
    if summary.get("annotation_labels"):
        for label, count in summary["annotation_labels"].items():
            lines.append(f"- `{label}`: `{count}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Annotation Outcomes", ""])
    if summary.get("annotation_outcomes"):
        for outcome, count in summary["annotation_outcomes"].items():
            lines.append(f"- `{outcome}`: `{count}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Skips", ""])
    skips = [record for record in report["records"] if not record.get("replayed")]
    if skips:
        for record in skips:
            label = record.get("event_type") or record.get("frame_type") or record.get("source_event_type")
            lines.append(f"- `{label}`: `{record.get('skip_reason')}`")
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: Path | None = None) -> tuple[Path, Path]:
    target_dir = output_dir or Path(report["recording_dir"])
    json_path = target_dir / "session_replay_report.json"
    markdown_path = target_dir / "session_replay_report.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
