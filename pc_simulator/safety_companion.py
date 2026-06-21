"""Safety Companion M0 adapter and deterministic mock router."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


CONTRACT_VERSION = "safety-companion.contract.v0.1"
MOCK_MODEL_VERSION = "safety-router-mock-0.1.0"


def evaluate(events: list[dict[str, Any]], device: dict[str, Any], *, now_ms: int | None = None) -> dict[str, Any]:
    model_input = build_model_input(events, device, now_ms=now_ms)
    model_output = mock_model_output(model_input)
    return {
        "model_input": model_input,
        "model_output": model_output,
    }


def build_model_input(
    events: list[dict[str, Any]],
    device: dict[str, Any],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    active_event = first_event_type(events)
    timestamp_ms = first_event_timestamp_ms(events) or now_ms or utc_now_ms()
    location_event = first_event_by_type(events, "location_report")
    sensor_event = first_event_by_type(events, "sensor_sample")
    battery = int_value(
        value_from_event_or_device(sensor_event, device, "battery"),
        default=int_value(device.get("battery"), 100),
    )

    model_input: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "timestamp_ms": timestamp_ms,
        "mode": mode_from_device(device),
        "motion": {
            "accel_window": [],
            "gyro_window": [],
            "stationary_seconds": stationary_seconds(events),
        },
        "audio": {
            "event_scores": audio_event_scores(events),
        },
        "location": location_context(location_event, device),
        "network": {
            "registered": bool(device.get("online", True)),
            "signal_level": signal_level(device.get("rssi")),
        },
        "device": {
            "battery_percent": clamp_int(battery, 0, 100),
            "base_online": bool(device.get("online", True)),
        },
    }
    if active_event:
        model_input["active_event"] = active_event
    return model_input


def mock_model_output(model_input: dict[str, Any]) -> dict[str, Any]:
    active_event = str(model_input.get("active_event") or "")
    device = model_input.get("device", {})
    location = model_input.get("location", {})
    audio = model_input.get("audio", {}).get("event_scores", {})

    if active_event in {"sos_pressed", "manual_sos"}:
        return output(
            risk_type="manual_sos",
            risk_score=1.0,
            confidence=1.0,
            recommended_action="escalate_emergency",
            evidence_request=["location_point", "device_log"],
            reason_codes=["manual_sos"],
        )

    if active_event == "location_report" and location.get("fix") is False:
        return output(
            risk_type="device_risk",
            risk_score=0.62,
            confidence=0.82,
            recommended_action="upload_summary",
            evidence_request=["device_log"],
            reason_codes=["gnss_no_fix"],
        )

    if int_value(device.get("battery_percent"), 100) <= 20:
        return output(
            risk_type="device_risk",
            risk_score=0.7,
            confidence=0.8,
            recommended_action="local_reminder",
            evidence_request=["device_log"],
            reason_codes=["low_battery"],
        )

    if float_value(audio.get("distress"), 0.0) >= 0.75:
        return output(
            risk_type="distress_audio",
            risk_score=0.86,
            confidence=0.76,
            recommended_action="ask_user_and_send_summary",
            evidence_request=["audio_5s", "location_point"],
            reason_codes=["distress_audio"],
        )

    if active_event == "wake_detected":
        return output(
            risk_type="none",
            risk_score=0.2,
            confidence=0.7,
            recommended_action="ask_user",
            evidence_request=["none"],
            reason_codes=["wake_detected"],
        )

    return output(
        risk_type="none",
        risk_score=0.0,
        confidence=0.9,
        recommended_action="ignore",
        evidence_request=["none"],
        reason_codes=["no_risk_signal"],
    )


def output(
    *,
    risk_type: str,
    risk_score: float,
    confidence: float,
    recommended_action: str,
    evidence_request: list[str],
    reason_codes: list[str],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "model_version": MOCK_MODEL_VERSION,
        "risk_type": risk_type,
        "risk_score": risk_score,
        "confidence": confidence,
        "recommended_action": recommended_action,
        "evidence_request": evidence_request,
        "reason_codes": reason_codes,
    }


def location_context(location_event: dict[str, Any] | None, device: dict[str, Any]) -> dict[str, Any]:
    source = location_event or device
    fix = bool(source.get("fix", True))
    if location_event and location_event.get("fix") is False:
        fix = False
    context: dict[str, Any] = {
        "fix": fix,
        "speed_mps": float_value(source.get("speed_mps"), 0.0),
        "accuracy_m": float_value(source.get("accuracy_m"), 999.0 if not fix else 10.0),
        "outside_safe_zone": bool(source.get("outside_safe_zone", False)),
    }
    if source.get("lat") is not None:
        context["lat"] = float_value(source.get("lat"), 0.0)
    if source.get("lon") is not None:
        context["lon"] = float_value(source.get("lon"), 0.0)
    return context


def audio_event_scores(events: list[dict[str, Any]]) -> dict[str, float]:
    wake = first_event_by_type(events, "wake_detected")
    if not wake:
        return {"speech": 0.0, "distress": 0.0, "impact": 0.0}
    confidence = float_value(wake.get("confidence"), 0.0)
    return {
        "speech": clamp_float(confidence, 0.0, 1.0),
        "distress": 0.0,
        "impact": 0.0,
    }


def stationary_seconds(events: list[dict[str, Any]]) -> float:
    for event in events:
        if event.get("stationary_seconds") is not None:
            return float_value(event.get("stationary_seconds"), 0.0)
    return 0.0


def first_event_type(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        event_type = event.get("event_type")
        if event_type and event_type != "mqtt_status":
            return str(event_type)
    return None


def first_event_by_type(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    return next((event for event in events if event.get("event_type") == event_type), None)


def first_event_timestamp_ms(events: list[dict[str, Any]]) -> int | None:
    for event in events:
        timestamp = timestamp_ms(event.get("received_at") or event.get("ts"))
        if timestamp is not None:
            return timestamp
    return None


def timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value)
    if text.isdigit():
        return int(text)
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def value_from_event_or_device(event: dict[str, Any] | None, device: dict[str, Any], field: str) -> Any:
    if event is not None and event.get(field) is not None:
        return event[field]
    return device.get(field)


def mode_from_device(device: dict[str, Any]) -> str:
    guard_mode = str(device.get("guard_mode") or "")
    if guard_mode in {"school_trip", "asset_guard", "elder_care"}:
        return guard_mode
    return "personal_safety"


def signal_level(rssi: Any) -> int:
    value = int_value(rssi, -120)
    if value >= -60:
        return 5
    if value >= -70:
        return 4
    if value >= -85:
        return 3
    if value >= -100:
        return 2
    if value > -120:
        return 1
    return 0


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


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
