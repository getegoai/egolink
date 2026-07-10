"""PC Simulator adapter for the Safety Companion M0 package."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from model_lab.safety_companion import RuleRouter, build_model_input
from model_lab.safety_companion.src.contract_validation import ContractValidationError, load_schema, validate_instance
from model_lab.safety_companion.src.event_builder import build_safety_event


CONTRACT_VERSION = "1.0.0"
ROUTER = RuleRouter()
REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_SUITE_PATH = REPO_ROOT / "model_lab" / "safety_companion" / "datasets" / "samples" / "scenario_suite.json"
DEFAULT_REPLAY_SCENARIOS = (
    "normal_walk",
    "manual_sos",
    "post_impact_inactivity",
    "privacy_restricted_impact",
)
EVALUABLE_EVENT_TYPES = {
    "sos_pressed",
    "manual_sos",
    "wake_detected",
    "sensor_sample",
    "location_report",
    "impact_detected",
    "post_impact_inactivity",
    "possible_fall",
    "distress_audio",
}


def evaluate_sensor_frame(sensor_frame: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a `sensor_frame` and return the standard `model_output`."""

    model_input = build_model_input(sensor_frame)
    return evaluate_model_input(model_input)


def evaluate_model_input(model_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a standard `model_input` through the packaged rule router."""

    return ROUTER.evaluate(model_input)


def evaluate_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate an HTTP request payload containing a sensor frame or model input."""

    value = dict(payload)
    if "sensor_frame" in value:
        return evaluate_sensor_frame_bundle(value["sensor_frame"])
    if "model_input" in value:
        return evaluate_model_input_bundle(value["model_input"])
    if value.get("contract_version") == CONTRACT_VERSION and "sensors" in value:
        return evaluate_sensor_frame_bundle(value)
    if value.get("contract_version") == CONTRACT_VERSION and "features" in value:
        return evaluate_model_input_bundle(value)
    raise ValueError("request body must contain `sensor_frame` or `model_input`")


def evaluate_model_input_bundle(model_input: Mapping[str, Any], *, sequence: int = 0) -> dict[str, Any]:
    """Evaluate a model input and include optional safety event/command records."""

    value = deepcopy(dict(model_input))
    model_output = evaluate_model_input(value)
    safety_event = build_safety_event(value, model_output, sequence=sequence)
    base_command = build_simulated_base_command(value, model_output, safety_event)
    return {
        "input_type": "model_input",
        "model_input": value,
        "model_output": model_output,
        "safety_event": safety_event,
        "base_command": base_command,
    }


def evaluate_sensor_frame_bundle(sensor_frame: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a sensor frame and include derived input and optional event."""

    frame = deepcopy(dict(sensor_frame))
    model_input = build_model_input(frame)
    model_output = evaluate_model_input(model_input)
    safety_event = build_safety_event(
        model_input,
        model_output,
        sequence=int(frame.get("sequence", 0)),
        sensor_frame=frame,
    )
    base_command = build_simulated_base_command(model_input, model_output, safety_event)
    return {
        "input_type": "sensor_frame",
        "sensor_frame": frame,
        "model_input": model_input,
        "model_output": model_output,
        "safety_event": safety_event,
        "base_command": base_command,
    }


def build_simulated_base_command(
    model_input: Mapping[str, Any],
    model_output: Mapping[str, Any],
    safety_event: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a no-side-effect command for user-facing safety actions."""

    action = str(model_output["recommended_action"])
    if action not in {"ask_user", "urgent_escalation"}:
        return None

    issued_at = int(model_input["timestamp_ms"])
    ttl = int(model_output["decision_ttl_ms"])
    urgent = action == "urgent_escalation"
    command = {
        "contract_version": CONTRACT_VERSION,
        "command_id": f"cmd-{model_output['output_id']}",
        "device_id": model_input["device_id"],
        "issued_at_ms": issued_at,
        "expires_at_ms": issued_at + ttl,
        "command": "ask_user",
        "args": {
            "prompt_kind": "urgent_check_in" if urgent else "safety_check_in",
            "risk_type": model_output["risk_type"],
            "priority": model_output["priority"],
            "recommended_action": action,
            "simulated": True,
            "no_external_side_effects": True,
        },
        "requires_user_consent": False,
        "safety_class": "emergency" if urgent else "reversible",
        "correlation_event_id": safety_event["event_id"] if safety_event else None,
    }
    validate_instance(command, load_schema("base_command.schema.json"))
    return command


def replay_scenarios(scenario_ids: list[str] | None = None) -> dict[str, Any]:
    """Replay packaged scenarios through the simulator adapter."""

    wanted = tuple(scenario_ids or DEFAULT_REPLAY_SCENARIOS)
    scenarios = {item["id"]: item for item in json.loads(SCENARIO_SUITE_PATH.read_text(encoding="utf-8"))}
    missing = [scenario_id for scenario_id in wanted if scenario_id not in scenarios]
    if missing:
        raise ValueError("unknown scenario id(s): " + ", ".join(missing))

    records: list[dict[str, Any]] = []
    for sequence, scenario_id in enumerate(wanted, start=1):
        scenario = scenarios[scenario_id]
        bundle = evaluate_model_input_bundle(scenario["input"], sequence=sequence)
        records.append(
            {
                "scenario_id": scenario_id,
                "description": scenario.get("description", ""),
                **bundle,
            }
        )
    return {
        "scenario_ids": list(wanted),
        "records": records,
        "summary": {
            "total": len(records),
            "safety_events": sum(1 for item in records if item["safety_event"] is not None),
            "base_commands": sum(1 for item in records if item["base_command"] is not None),
        },
    }


def evaluate(events: list[dict[str, Any]], device: dict[str, Any], *, now_ms: int | None = None) -> dict[str, Any]:
    """Evaluate the latest simulator state for `/api/state`."""

    sensor_frame = build_sensor_frame(events, device, now_ms=now_ms)
    return evaluate_sensor_frame_bundle(sensor_frame)


def evaluate_event(event: Mapping[str, Any], device: Mapping[str, Any], *, now_ms: int | None = None) -> dict[str, Any]:
    """Evaluate a single device/simulator event through the Safety Companion flow."""

    sensor_frame = build_sensor_frame([dict(event)], device, now_ms=now_ms)
    bundle = evaluate_sensor_frame_bundle(sensor_frame)
    bundle["source_event_key"] = source_event_key(event)
    bundle["source_event_type"] = event.get("event_type")
    return bundle


def is_evaluable_event(event: Mapping[str, Any]) -> bool:
    return str(event.get("event_type") or "") in EVALUABLE_EVENT_TYPES


def source_event_key(event: Mapping[str, Any]) -> str:
    device_id = str(event.get("device_id") or "")
    event_type = str(event.get("event_type") or event.get("message_type") or "")
    seq = str(event.get("seq") or "")
    timestamp = str(event.get("ts") or event.get("received_at") or "")
    return f"{device_id}:{event_type}:{seq}:{timestamp}"


def build_sensor_frame(
    events: list[dict[str, Any]],
    device: Mapping[str, Any],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    active_event = first_relevant_event(events)
    timestamp = first_event_timestamp_ms([active_event] if active_event else []) or now_ms or utc_now_ms()
    sequence = int_value((active_event or {}).get("seq"), int_value(device.get("seq"), 0))
    frame_id = f"pcsim-{sequence}-{timestamp}"

    return {
        "contract_version": CONTRACT_VERSION,
        "frame_id": frame_id,
        "device_id": str(device.get("device_id") or (active_event or {}).get("device_id") or "ego-link-001"),
        "timestamp_ms": timestamp,
        "monotonic_ms": None,
        "sequence": max(0, sequence),
        "mode": mode_from_device(device),
        "source": source_from_event(active_event),
        "sensors": {
            "motion": motion_sensor(active_event, device),
            "audio": audio_sensor(active_event),
            "location": location_sensor(active_event, device),
            "network": network_sensor(active_event, device),
            "device": device_sensor(active_event, device),
            "user_input": user_input_sensor(active_event),
        },
        "metadata": {
            "source_event_type": (active_event or {}).get("event_type"),
            "source_message_type": (active_event or {}).get("message_type"),
        },
    }


def motion_sensor(event: Mapping[str, Any] | None, device: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str((event or {}).get("event_type") or "")
    impact_score = float_value((event or {}).get("impact_score"), 0.0)
    fall_score = float_value((event or {}).get("fall_score"), 0.0)
    stationary_seconds = float_value((event or {}).get("stationary_seconds"), 0.0)
    label = str((event or {}).get("activity_label") or "unknown")

    if event_type in {"impact_detected", "post_impact_inactivity"}:
        label = "impact"
        impact_score = max(impact_score, 0.92)
        stationary_seconds = max(stationary_seconds, 20.0)
    elif event_type in {"possible_fall", "fall_detected"}:
        label = "fall_candidate"
        fall_score = max(fall_score, 0.91)
    elif label == "unknown" and float_value((event or device).get("speed_mps"), 0.0) > 0.2:
        label = "walking"

    return {
        "sample_rate_hz": 50.0,
        "window_duration_ms": 2560,
        "accel_mps2": None,
        "gyro_rad_s": None,
        "raw_ref": None,
        "summary": {
            "activity_label": label,
            "activity_confidence": float_value((event or {}).get("activity_confidence"), 0.9 if label != "unknown" else 0.0),
            "max_accel_g": float_value((event or {}).get("max_accel_g"), 1.2),
            "jerk_peak_g_s": float_value((event or {}).get("jerk_peak_g_s"), 2.0),
            "orientation_change_deg": float_value((event or {}).get("orientation_change_deg"), 0.0),
            "impact_score": clamp_float(impact_score, 0.0, 1.0),
            "fall_score": clamp_float(fall_score, 0.0, 1.0),
            "stationary_seconds": max(0.0, stationary_seconds),
            "device_worn": bool_value((event or {}).get("device_worn"), True),
        },
    }


def audio_sensor(event: Mapping[str, Any] | None) -> dict[str, Any]:
    event_type = str((event or {}).get("event_type") or "")
    speech = float_value((event or {}).get("speech_score"), 0.0)
    distress = float_value((event or {}).get("distress_score"), 0.0)
    impact = float_value((event or {}).get("impact_sound_score"), 0.0)
    loud = float_value((event or {}).get("unknown_loud_sound_score"), 0.0)

    if event_type == "wake_detected":
        speech = max(speech, float_value((event or {}).get("confidence"), 0.0))
    elif event_type == "distress_audio":
        distress = max(distress, 0.91)
    elif event_type in {"impact_detected", "post_impact_inactivity"}:
        impact = max(impact, 0.76)

    return {
        "sample_rate_hz": 16000,
        "window_duration_ms": 1000,
        "vad_probability": clamp_float(speech, 0.0, 1.0),
        "rms_dbfs": -48.0,
        "peak_dbfs": -31.0,
        "quality_score": float_value((event or {}).get("audio_quality_score"), 0.9),
        "event_scores": {
            "speech": clamp_float(speech, 0.0, 1.0),
            "distress": clamp_float(distress, 0.0, 1.0),
            "impact": clamp_float(impact, 0.0, 1.0),
            "unknown_loud_sound": clamp_float(loud, 0.0, 1.0),
        },
        "clip_ref": (event or {}).get("audio_clip_ref"),
    }


def location_sensor(event: Mapping[str, Any] | None, device: Mapping[str, Any]) -> dict[str, Any]:
    source = event if event and event.get("event_type") == "location_report" else device
    fix_valid = bool_value(source.get("fix"), str(source.get("gnss_state") or "") not in {"no_fix", "off"})
    quality = 0.85 if fix_valid else 0.0
    return {
        "fix_valid": fix_valid,
        "latitude_deg": optional_float(source.get("lat")),
        "longitude_deg": optional_float(source.get("lon")),
        "speed_mps": max(0.0, float_value(source.get("speed_mps"), 0.0)),
        "heading_deg": optional_float(source.get("heading_deg")),
        "accuracy_m": optional_float(source.get("accuracy_m")),
        "fix_age_ms": int_value(source.get("fix_age_ms"), 1000) if fix_valid else None,
        "outside_safe_zone": bool_value(source.get("outside_safe_zone"), False),
        "dwell_seconds": max(0.0, float_value(source.get("dwell_seconds"), 0.0)),
        "route_deviation_m": max(0.0, float_value(source.get("route_deviation_m"), 0.0)),
        "quality_score": clamp_float(float_value(source.get("location_quality_score"), quality), 0.0, 1.0),
    }


def network_sensor(event: Mapping[str, Any] | None, device: Mapping[str, Any]) -> dict[str, Any]:
    online = bool_value(device.get("online"), True)
    event_rssi = (event or {}).get("rssi")
    if event_rssi is None:
        event_rssi = (event or {}).get("wifi_rssi")
    rssi = int_value(event_rssi, int_value(device.get("rssi"), -120))
    level = min(4, signal_level(rssi))
    return {
        "registered": online,
        "link_type": link_type_from_device(device),
        "rssi_dbm": rssi if rssi > -160 else None,
        "signal_level": level,
        "round_trip_ms": optional_float((event or {}).get("round_trip_ms")),
        "upload_available": online,
        "base_online": online,
        "offline_seconds": 0.0 if online else float_value(device.get("offline_seconds"), 1200.0),
    }


def device_sensor(event: Mapping[str, Any] | None, device: Mapping[str, Any]) -> dict[str, Any]:
    battery = float_value((event or {}).get("battery"), float_value(device.get("battery"), 100.0))
    return {
        "battery_percent": clamp_float(battery, 0.0, 100.0),
        "charging": bool_value((event or {}).get("charging"), bool_value(device.get("charging"), False)),
        "temperature_c": optional_float((event or {}).get("temperature_c")),
        "privacy_mode": bool_value((event or {}).get("privacy_mode"), bool_value(device.get("privacy_mode"), False)),
        "camera_available": bool_value(device.get("camera_available"), True),
        "microphone_available": bool_value(device.get("microphone_available"), True),
    }


def user_input_sensor(event: Mapping[str, Any] | None) -> dict[str, Any]:
    event_type = str((event or {}).get("event_type") or "")
    return {
        "sos_pressed": event_type in {"sos_pressed", "manual_sos"} or bool_value((event or {}).get("sos_pressed"), False),
        "cancel_pressed": bool_value((event or {}).get("cancel_pressed"), False),
        "response": str((event or {}).get("response") or "none"),
    }


def first_relevant_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    ignored = {"mqtt_status", "mqtt_ack", "command_sent", "heartbeat", "safety_evaluation", "safety_event"}
    return next((event for event in events if event.get("event_type") not in ignored), None)


def first_event_timestamp_ms(events: list[Mapping[str, Any]]) -> int | None:
    for event in events:
        timestamp = timestamp_ms(event.get("received_at") or event.get("ts"))
        if timestamp is not None:
            return timestamp
    return None


def timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def mode_from_device(device: Mapping[str, Any]) -> str:
    mode = str(device.get("guard_mode") or "")
    if mode in {"personal_safety", "child_safety", "elder_safety", "cycling", "test"}:
        return mode
    return "personal_safety"


def source_from_event(event: Mapping[str, Any] | None) -> str:
    if event and event.get("ingest_source"):
        return "device"
    return "simulator"


def link_type_from_device(device: Mapping[str, Any]) -> str:
    link_type = str(device.get("link_type") or "unknown")
    if "wifi" in link_type:
        return "wifi_mock"
    if "lte" in link_type or "4g" in link_type:
        return "lte"
    if link_type in {"ble", "offline", "unknown"}:
        return link_type
    return "unknown"


def signal_level(rssi: Any) -> int:
    value = int_value(rssi, -120)
    if value >= -60:
        return 4
    if value >= -70:
        return 3
    if value >= -85:
        return 2
    if value > -120:
        return 1
    return 0


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


def int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float_value(value, 0.0)


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def error_message(error: Exception) -> str:
    if isinstance(error, ContractValidationError):
        return str(error)
    return f"{type(error).__name__}: {error}"
