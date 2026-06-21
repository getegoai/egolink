"""Quality gate for Ego Link M1 session recordings."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPORT_SCHEMA_VERSION = "egolink.session_quality_report.v0.1"
EXPECTED_SCHEMA_VERSION = "egolink.session_recording.v0.1"
REQUIRED_FILES = {
    "manifest": "session_manifest.json",
    "sensor_frames": "sensor_frames.jsonl",
    "events": "events.jsonl",
    "annotations": "annotations.jsonl",
}
REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "recorder_version",
    "session_id",
    "created_at",
    "source_event_log",
    "device_ids",
    "board_target",
    "firmware",
    "privacy",
    "sensor_sources",
    "record_counts",
    "outputs",
}
REQUIRED_SENSOR_SOURCES = {
    "sensor_sample/device_health",
    "mqtt_status",
    "wifi_rssi",
    "sim7670g_gnss",
    "mock_gnss",
    "safety_companion_m0",
    "camera_single_frame",
    "imu",
    "microphone",
    "physical_sos_gpio",
    "sd_storage",
    "battery_telemetry",
    "esp32_side_sim7670g_control",
}
DISALLOWED_REAL_SOURCES = {
    "imu",
    "microphone",
    "physical_sos_gpio",
    "sd_storage",
    "esp32_side_sim7670g_control",
}
ALLOWED_FRAME_TYPES = {"device_status", "device_health", "gnss_report"}
ALLOWED_FRAME_AVAILABILITY = {"real", "pc_side_probe"}
ALLOWED_EVENT_TYPES = {
    "sos_pressed",
    "wake_detected",
    "safety_evaluation",
    "safety_event",
    "command_sent",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_issue(code: str, message: str, *, path: str | None = None) -> dict[str, str]:
    issue = {"code": code, "message": message}
    if path is not None:
        issue["path"] = path
    return issue


def load_json(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [make_issue("missing_file", f"Missing file: {path.name}", path=str(path))]
    except json.JSONDecodeError as exc:
        return None, [make_issue("invalid_json", f"Invalid JSON: {exc.msg}", path=str(path))]
    if not isinstance(payload, dict):
        return None, [make_issue("invalid_json_object", "Expected a JSON object.", path=str(path))]
    return payload, []


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], [make_issue("missing_file", f"Missing file: {path.name}", path=str(path))]
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(
                make_issue(
                    "invalid_jsonl",
                    f"Invalid JSONL row {index}: {exc.msg}",
                    path=f"{path}:{index}",
                )
            )
            continue
        if not isinstance(value, dict):
            issues.append(
                make_issue(
                    "invalid_jsonl_object",
                    f"JSONL row {index} must be an object.",
                    path=f"{path}:{index}",
                )
            )
            continue
        rows.append(value)
    return rows, issues


def inspect_recording(recording_dir: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    recording_dir = recording_dir.resolve()
    generated = generated_at or utc_now()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    file_paths = {name: recording_dir / filename for name, filename in REQUIRED_FILES.items()}
    for name, path in file_paths.items():
        if not path.exists():
            errors.append(make_issue("missing_file", f"Missing required {name} file.", path=str(path)))

    manifest, manifest_errors = load_json(file_paths["manifest"])
    errors.extend(manifest_errors)
    sensor_frames, sensor_frame_errors = load_jsonl(file_paths["sensor_frames"])
    events, event_errors = load_jsonl(file_paths["events"])
    annotations, annotation_errors = load_jsonl(file_paths["annotations"])
    errors.extend(sensor_frame_errors)
    errors.extend(event_errors)
    errors.extend(annotation_errors)

    if manifest is not None:
        validate_manifest(manifest, errors, warnings)
        validate_record_counts(manifest, sensor_frames, events, annotations, errors)
        validate_privacy(manifest, errors)
        validate_sensor_sources(manifest, errors, warnings)

    validate_sensor_frames(sensor_frames, errors, warnings)
    validate_events(events, errors, warnings)
    validate_annotations(annotations, errors, warnings)
    validate_unique_source_keys(sensor_frames + events, errors)
    validate_seq_and_time(sensor_frames + events, warnings)

    quality_score = compute_quality_score(errors, warnings)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated,
        "recording_dir": str(recording_dir),
        "passed": not errors,
        "quality_score": quality_score,
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "sensor_frames": len(sensor_frames),
            "events": len(events),
            "annotations": len(annotations),
            "frame_types": dict(sorted(Counter(str(row.get("frame_type", "unknown")) for row in sensor_frames).items())),
            "event_types": dict(sorted(Counter(str(row.get("event_type", "unknown")) for row in events).items())),
        },
        "errors": errors,
        "warnings": warnings,
    }


def validate_manifest(
    manifest: dict[str, Any],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    for field in missing:
        errors.append(make_issue("manifest_missing_field", f"Manifest is missing `{field}`."))
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(
            make_issue(
                "manifest_schema_version",
                f"Expected schema_version `{EXPECTED_SCHEMA_VERSION}`, got `{manifest.get('schema_version')}`.",
            )
        )
    if not manifest.get("session_id"):
        errors.append(make_issue("manifest_session_id", "Manifest session_id is required."))
    if manifest.get("firmware", {}).get("version") in (None, "", "unknown"):
        warnings.append(make_issue("firmware_version_unknown", "Firmware version is unknown."))


def validate_record_counts(
    manifest: dict[str, Any],
    sensor_frames: list[dict[str, Any]],
    events: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> None:
    counts = manifest.get("record_counts")
    if not isinstance(counts, dict):
        errors.append(make_issue("record_counts_missing", "Manifest record_counts must be an object."))
        return
    expected = {
        "sensor_frames": len(sensor_frames),
        "events": len(events),
        "annotations": len(annotations),
    }
    for name, actual in expected.items():
        if counts.get(name) != actual:
            errors.append(
                make_issue(
                    "record_count_mismatch",
                    f"record_counts.{name}={counts.get(name)} but file has {actual}.",
                )
            )


def validate_privacy(manifest: dict[str, Any], errors: list[dict[str, str]]) -> None:
    privacy = manifest.get("privacy")
    if not isinstance(privacy, dict):
        errors.append(make_issue("privacy_missing", "Manifest privacy must be an object."))
        return
    if privacy.get("mode") != "structured_only":
        errors.append(make_issue("privacy_mode", "Recorder must use structured_only privacy mode."))
    if privacy.get("raw_audio_allowed") is not False:
        errors.append(make_issue("raw_audio_allowed", "raw_audio_allowed must be false."))
    if privacy.get("raw_image_allowed") is not False:
        errors.append(make_issue("raw_image_allowed", "raw_image_allowed must be false."))


def validate_sensor_sources(
    manifest: dict[str, Any],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    sources = manifest.get("sensor_sources")
    if not isinstance(sources, dict):
        errors.append(make_issue("sensor_sources_missing", "Manifest sensor_sources must be an object."))
        return
    missing = sorted(REQUIRED_SENSOR_SOURCES - set(sources))
    for source in missing:
        errors.append(make_issue("sensor_source_missing", f"Missing sensor source `{source}`."))
    for source in DISALLOWED_REAL_SOURCES:
        value = sources.get(source)
        if not isinstance(value, dict):
            continue
        if value.get("availability") == "real":
            errors.append(make_issue("unverified_source_marked_real", f"`{source}` must not be marked real."))
    battery = sources.get("battery_telemetry")
    if isinstance(battery, dict) and battery.get("availability") == "real":
        errors.append(make_issue("battery_marked_real", "battery_telemetry must remain mock until verified."))
    camera = sources.get("camera_single_frame")
    if isinstance(camera, dict) and camera.get("availability") not in {"disabled", "not_available"}:
        warnings.append(make_issue("camera_enabled", "Camera is semi-verified but should stay disabled in M1-002 recordings."))


def validate_sensor_frames(
    sensor_frames: list[dict[str, Any]],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    if not sensor_frames:
        warnings.append(make_issue("no_sensor_frames", "Recording contains no sensor frames."))
    for index, frame in enumerate(sensor_frames, start=1):
        prefix = f"sensor_frames[{index}]"
        if frame.get("record_type") != "sensor_frame":
            errors.append(make_issue("frame_record_type", f"{prefix} record_type must be sensor_frame."))
        if frame.get("frame_type") not in ALLOWED_FRAME_TYPES:
            errors.append(make_issue("frame_type", f"{prefix} has unsupported frame_type `{frame.get('frame_type')}`."))
        if frame.get("source_availability") not in ALLOWED_FRAME_AVAILABILITY:
            errors.append(
                make_issue(
                    "frame_source_availability",
                    f"{prefix} has unsupported source_availability `{frame.get('source_availability')}`.",
                )
            )
        for field in ["source_event_key", "source_event_type", "device_id"]:
            if not frame.get(field):
                errors.append(make_issue("frame_missing_field", f"{prefix} is missing `{field}`."))
        if "ts" not in frame and "received_at" not in frame and "monotonic_ms" not in frame:
            warnings.append(make_issue("frame_missing_time", f"{prefix} has no timestamp field."))


def validate_events(
    events: list[dict[str, Any]],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    for index, event in enumerate(events, start=1):
        prefix = f"events[{index}]"
        if event.get("record_type") != "event":
            errors.append(make_issue("event_record_type", f"{prefix} record_type must be event."))
        if event.get("event_type") not in ALLOWED_EVENT_TYPES:
            errors.append(make_issue("event_type", f"{prefix} has unsupported event_type `{event.get('event_type')}`."))
        for field in ["source_event_key", "source_event_type", "device_id"]:
            if not event.get(field):
                errors.append(make_issue("event_missing_field", f"{prefix} is missing `{field}`."))
        if event.get("event_type") in {"safety_evaluation", "safety_event"} and not event.get("risk_type"):
            warnings.append(make_issue("safety_event_missing_risk", f"{prefix} has no risk_type."))


def validate_annotations(
    annotations: list[dict[str, Any]],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    if not annotations:
        warnings.append(make_issue("annotations_empty", "Annotations file is present but empty."))
        return
    for index, annotation in enumerate(annotations, start=1):
        prefix = f"annotations[{index}]"
        for field in ["session_id", "source_event_key", "label", "created_at"]:
            if not annotation.get(field):
                errors.append(make_issue("annotation_missing_field", f"{prefix} is missing `{field}`."))


def validate_unique_source_keys(rows: list[dict[str, Any]], errors: list[dict[str, str]]) -> None:
    keys: dict[str, list[str]] = defaultdict(list)
    for index, row in enumerate(rows, start=1):
        key = row.get("source_event_key")
        if not key:
            continue
        keys[str(key)].append(f"row {index}")
    for key, locations in sorted(keys.items()):
        if len(locations) > 1:
            errors.append(
                make_issue(
                    "duplicate_source_event_key",
                    f"Duplicate source_event_key `{key}` appears {len(locations)} times.",
                )
            )


def validate_seq_and_time(rows: list[dict[str, Any]], warnings: list[dict[str, str]]) -> None:
    last_seq_by_stream: dict[tuple[str, str], int] = {}
    last_time_by_stream: dict[tuple[str, str], str] = {}
    seq_warned: set[tuple[str, str]] = set()
    time_warned: set[tuple[str, str]] = set()
    for row in rows:
        device_id = str(row.get("device_id") or "unknown")
        stream = str(row.get("source_event_type") or row.get("frame_type") or row.get("event_type") or "unknown")
        stream_key = (device_id, stream)
        seq = row.get("seq")
        if isinstance(seq, int):
            last_seq = last_seq_by_stream.get(stream_key)
            if last_seq is not None and seq < last_seq and stream_key not in seq_warned:
                warnings.append(
                    make_issue(
                        "seq_decrease",
                        f"seq decreased for {device_id}/{stream}: {last_seq} -> {seq}.",
                    )
                )
                seq_warned.add(stream_key)
            last_seq_by_stream[stream_key] = seq
        timestamp = str(row.get("received_at") or row.get("ts") or "")
        if not timestamp or timestamp.startswith("uptime_ms:"):
            continue
        last_time = last_time_by_stream.get(stream_key)
        if last_time is not None and timestamp < last_time and stream_key not in time_warned:
            warnings.append(
                make_issue(
                    "timestamp_decrease",
                    f"timestamp decreased for {device_id}/{stream}: {last_time} -> {timestamp}.",
                )
            )
            time_warned.add(stream_key)
        last_time_by_stream[stream_key] = timestamp


def compute_quality_score(errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> float:
    score = 1.0 - (0.2 * len(errors)) - (0.03 * len(warnings))
    return round(max(score, 0.0), 3)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Ego Link Session Quality Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Recording dir: `{report['recording_dir']}`",
        f"- Passed: `{report['passed']}`",
        f"- Quality score: `{report['quality_score']}`",
        f"- Errors: `{summary['errors']}`",
        f"- Warnings: `{summary['warnings']}`",
        f"- Sensor frames: `{summary['sensor_frames']}`",
        f"- Events: `{summary['events']}`",
        f"- Annotations: `{summary['annotations']}`",
        "",
        "## Frame Types",
        "",
    ]
    for frame_type, count in summary.get("frame_types", {}).items():
        lines.append(f"- `{frame_type}`: `{count}`")
    if not summary.get("frame_types"):
        lines.append("- None.")
    lines.extend(["", "## Event Types", ""])
    for event_type, count in summary.get("event_types", {}).items():
        lines.append(f"- `{event_type}`: `{count}`")
    if not summary.get("event_types"):
        lines.append("- None.")
    lines.extend(["", "## Errors", ""])
    if report["errors"]:
        for issue in report["errors"]:
            lines.append(f"- `{issue['code']}`: {issue['message']}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        for issue in report["warnings"]:
            lines.append(f"- `{issue['code']}`: {issue['message']}")
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: Path | None = None) -> tuple[Path, Path]:
    target_dir = output_dir or Path(report["recording_dir"])
    json_path = target_dir / "session_quality_report.json"
    markdown_path = target_dir / "session_quality_report.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
