"""Session recorder utilities for Ego Link M1 data foundation.

This module derives a structured recording from the existing PC Simulator
event log. It does not talk to hardware, start sensors, or infer capabilities
that are not present in the hardware matrix.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from pc_simulator import event_store, protocol


RECORDER_VERSION = "m1-002.0"
DEFAULT_BOARD_TARGET = "waveshare_esp32s3_sim7670g_4g"
DEFAULT_CONTRACT_VERSION = protocol.PROTOCOL_VERSION
UPTIME_RE = re.compile(r"^uptime_ms:(?P<value>\d+)$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_sensor_sources() -> dict[str, dict[str, Any]]:
    return {
        "sensor_sample/device_health": {
            "availability": "real",
            "status": "verified",
            "source": "firmware/mqtt_heartbeat",
            "records": ["wifi_rssi", "free_heap_bytes", "min_free_heap_bytes", "uptime_ms"],
        },
        "mqtt_status": {
            "availability": "real",
            "status": "verified",
            "source": "firmware/mqtt_heartbeat",
            "records": ["battery_mock", "charging_mock", "guard_mode", "queue_size"],
        },
        "wifi_rssi": {
            "availability": "real",
            "status": "verified",
            "source": "esp_wifi_sta_get_ap_info",
        },
        "sim7670g_gnss": {
            "availability": "pc_side_probe",
            "status": "pc_side_verified",
            "source": "scripts/sim7670_gnss_probe.py",
            "records": ["fix", "gnss_power_state", "satellites"],
        },
        "mock_gnss": {
            "availability": "mock",
            "status": "mock_only",
            "source": "firmware/dashboard mock",
        },
        "safety_companion_m0": {
            "availability": "rule_baseline",
            "status": "verified",
            "source": "pc_simulator/safety_companion.py",
        },
        "camera_single_frame": {
            "availability": "disabled",
            "status": "semi_verified",
            "source": "firmware/camera_smoke",
            "note": "camera smoke is not part of this recorder path",
        },
        "imu": {
            "availability": "not_available",
            "status": "missing_or_unknown",
        },
        "microphone": {
            "availability": "not_available",
            "status": "missing_or_unknown",
        },
        "physical_sos_gpio": {
            "availability": "not_available",
            "status": "not_verified",
        },
        "sd_storage": {
            "availability": "not_available",
            "status": "not_verified",
        },
        "battery_telemetry": {
            "availability": "mock",
            "status": "mock_only",
            "note": "current firmware payload uses battery=87 and charging=false placeholders",
        },
        "esp32_side_sim7670g_control": {
            "availability": "not_available",
            "status": "not_verified",
        },
    }


def parse_monotonic_ms(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    match = UPTIME_RE.match(value)
    if match is None:
        return None
    return int(match.group("value"))


def source_event_key(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or event.get("message_type") or "unknown")
    device_id = str(event.get("device_id") or protocol.DEVICE_ID)
    seq = event.get("seq")
    if seq not in (None, ""):
        return f"{device_id}:{event_type}:{seq}"
    timestamp = str(event.get("received_at") or event.get("ts") or "")
    return f"{device_id}:{event_type}:{timestamp}"


def compact_base_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_event_key": source_event_key(event),
        "source_event_type": str(event.get("event_type") or event.get("message_type") or "unknown"),
        "device_id": str(event.get("device_id") or protocol.DEVICE_ID),
        "seq": event.get("seq"),
        "ts": event.get("ts"),
        "received_at": event.get("received_at"),
    }


def device_health_frame(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event_type") != "sensor_sample":
        return None
    if event.get("sensor_kind") not in (None, "device_health"):
        return None
    frame = compact_base_event(event)
    frame.update(
        {
            "record_type": "sensor_frame",
            "frame_type": "device_health",
            "source_availability": "real",
            "source_status": "verified",
            "monotonic_ms": parse_monotonic_ms(event.get("ts") or event.get("uptime_ms")),
            "wifi_rssi": event.get("wifi_rssi"),
            "free_heap_bytes": event.get("free_heap_bytes"),
            "min_free_heap_bytes": event.get("min_free_heap_bytes"),
            "battery": event.get("battery"),
            "charging": event.get("charging"),
            "modem_state": event.get("modem_state"),
            "gnss_state": event.get("gnss_state"),
        }
    )
    return drop_none(frame)


def status_frame(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event_type") != "mqtt_status" and event.get("message_type") != "status":
        return None
    frame = compact_base_event(event)
    frame.update(
        {
            "record_type": "sensor_frame",
            "frame_type": "device_status",
            "source_availability": "real",
            "source_status": "verified",
            "monotonic_ms": parse_monotonic_ms(event.get("ts")),
            "battery": event.get("battery"),
            "charging": event.get("charging"),
            "link_type": event.get("link_type"),
            "guard_mode": event.get("guard_mode"),
            "queue_size": event.get("queue_size"),
            "wifi_rssi": event.get("rssi") or event.get("wifi_rssi"),
            "modem_state": event.get("modem_state"),
            "gnss_state": event.get("gnss_state"),
        }
    )
    return drop_none(frame)


def gnss_frame(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event_type") != "location_report":
        return None
    source = str(event.get("source") or "")
    if source not in {"sim7670g_gnss", "pc_at_probe"} and "gnss_power_state" not in event:
        return None
    frame = compact_base_event(event)
    frame.update(
        {
            "record_type": "sensor_frame",
            "frame_type": "gnss_report",
            "source_availability": "pc_side_probe",
            "source_status": "pc_side_verified",
            "fix": event.get("fix"),
            "lat": event.get("lat"),
            "lon": event.get("lon"),
            "accuracy_m": event.get("accuracy_m"),
            "speed_mps": event.get("speed_mps"),
            "satellites": event.get("satellites"),
            "gnss_power_state": event.get("gnss_power_state"),
            "gnss_state": event.get("gnss_state"),
        }
    )
    return drop_none(frame)


def sensor_frame_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    for builder in (device_health_frame, status_frame, gnss_frame):
        frame = builder(event)
        if frame is not None:
            return frame
    return None


def recorder_event_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or "")
    if event_type not in {
        "sos_pressed",
        "wake_detected",
        "safety_evaluation",
        "safety_event",
        "command_sent",
    }:
        return None
    record = compact_base_event(event)
    record.update(
        {
            "record_type": "event",
            "event_type": event_type,
            "priority": event.get("priority"),
            "source": event.get("source"),
            "risk_type": event.get("risk_type"),
            "risk_score": event.get("risk_score"),
            "confidence": event.get("confidence"),
            "recommended_action": event.get("recommended_action"),
            "command": event.get("cmd") or event.get("command"),
            "command_id": event.get("command_id") or event.get("cmd_id"),
            "source_event_key_ref": event.get("source_event_key"),
            "source_event_type_ref": event.get("source_event_type"),
        }
    )
    return drop_none(record)


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def event_time(event: dict[str, Any]) -> str:
    return str(event.get("received_at") or event.get("ts") or "")


def build_manifest(
    *,
    session_id: str,
    created_at: str,
    event_log: Path,
    events: list[dict[str, Any]],
    sensor_frames: list[dict[str, Any]],
    recorder_events: list[dict[str, Any]],
) -> dict[str, Any]:
    device_ids = sorted({str(event.get("device_id")) for event in events if event.get("device_id")})
    counts = Counter(str(event.get("event_type") or event.get("message_type") or "unknown") for event in events)
    return {
        "schema_version": "egolink.session_recording.v0.1",
        "recorder_version": RECORDER_VERSION,
        "session_id": session_id,
        "created_at": created_at,
        "source_event_log": str(event_log),
        "device_ids": device_ids or [protocol.DEVICE_ID],
        "board_target": DEFAULT_BOARD_TARGET,
        "firmware": {
            "name": "mqtt_heartbeat",
            "version": "unknown",
            "contract_version": DEFAULT_CONTRACT_VERSION,
        },
        "privacy": {
            "mode": "structured_only",
            "raw_audio_allowed": False,
            "raw_image_allowed": False,
            "notes": "No raw audio or image capture is started by the M1-002 recorder.",
        },
        "sensor_sources": default_sensor_sources(),
        "record_counts": {
            "source_events": len(events),
            "sensor_frames": len(sensor_frames),
            "events": len(recorder_events),
            "annotations": 0,
        },
        "source_event_counts": dict(sorted(counts.items())),
        "outputs": {
            "manifest": "session_manifest.json",
            "sensor_frames": "sensor_frames.jsonl",
            "events": "events.jsonl",
            "annotations": "annotations.jsonl",
            "summary": "session_recording.md",
        },
        "limitations": [
            "IMU, microphone, physical SOS GPIO, SD storage, true battery telemetry, and ESP32-side SIM7670G control are not recorded as real sources.",
            "Safety Companion M0 records are deterministic rule-baseline outputs, not trained model labels.",
            "GNSS records are PC-side AT probe reports until ESP32-side SIM7670G control is implemented.",
        ],
    }


def build_recording(
    events: list[dict[str, Any]],
    *,
    event_log: Path,
    session_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or utc_now()
    ordered_events = list(events)
    sensor_frames = [
        frame
        for event in ordered_events
        for frame in [sensor_frame_from_event(event)]
        if frame is not None
    ]
    recorder_events = [
        record
        for event in ordered_events
        for record in [recorder_event_from_event(event)]
        if record is not None
    ]
    manifest = build_manifest(
        session_id=session_id,
        created_at=created,
        event_log=event_log,
        events=ordered_events,
        sensor_frames=sensor_frames,
        recorder_events=recorder_events,
    )
    return {
        "manifest": manifest,
        "sensor_frames": sensor_frames,
        "events": recorder_events,
        "annotations": [],
    }


def build_recording_from_log(
    event_log: Path,
    *,
    session_id: str,
    limit: int = 200,
    created_at: str | None = None,
) -> dict[str, Any]:
    events = event_store.load_recent(event_log, limit=limit)
    return build_recording(
        list(reversed(events)),
        event_log=event_log,
        session_id=session_id,
        created_at=created_at,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def render_markdown(recording: dict[str, Any]) -> str:
    manifest = recording["manifest"]
    counts = manifest["record_counts"]
    sensor_sources = manifest["sensor_sources"]
    lines = [
        "# Ego Link Session Recording",
        "",
        f"- Session ID: `{manifest['session_id']}`",
        f"- Created: `{manifest['created_at']}`",
        f"- Source event log: `{manifest['source_event_log']}`",
        f"- Sensor frames: `{counts['sensor_frames']}`",
        f"- Events: `{counts['events']}`",
        f"- Annotations: `{counts['annotations']}`",
        "",
        "## Source Availability",
        "",
    ]
    for name in sorted(sensor_sources):
        source = sensor_sources[name]
        lines.append(
            f"- `{name}`: `{source.get('availability')}` / `{source.get('status')}`"
        )
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- No raw audio or image capture is started.",
            "- IMU, microphone, physical SOS GPIO, SD, true battery telemetry, and ESP32-side SIM7670G control remain unavailable or unverified.",
            "- Safety Companion M0 outputs are deterministic rule-baseline records.",
            "",
        ]
    )
    return "\n".join(lines)


def write_recording(recording: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest": output_dir / "session_manifest.json",
        "sensor_frames": output_dir / "sensor_frames.jsonl",
        "events": output_dir / "events.jsonl",
        "annotations": output_dir / "annotations.jsonl",
        "summary": output_dir / "session_recording.md",
    }
    write_json(paths["manifest"], recording["manifest"])
    write_jsonl(paths["sensor_frames"], recording["sensor_frames"])
    write_jsonl(paths["events"], recording["events"])
    write_jsonl(paths["annotations"], recording["annotations"])
    paths["summary"].write_text(render_markdown(recording), encoding="utf-8")
    return paths
