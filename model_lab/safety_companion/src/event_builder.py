"""Build a transport event from a router result and optional sensor evidence."""

from __future__ import annotations

from typing import Any, Mapping

from .contract_validation import load_schema, validate_instance


def build_safety_event(
    model_input: Mapping[str, Any],
    model_output: Mapping[str, Any],
    *,
    sequence: int,
    sensor_frame: Mapping[str, Any] | None = None,
    validate: bool = True,
) -> dict[str, Any] | None:
    """Create a SafetyEvent for non-empty risk results.

    ``none`` results are intentionally not converted into network events. Device
    status/heartbeat transport remains a firmware concern.
    """

    if model_output["risk_type"] == "none":
        return None

    features = model_input["features"]
    device = features["device"]
    network = features["network"]
    location_data = (sensor_frame or {}).get("sensors", {}).get("location") or {}
    motion_data = (sensor_frame or {}).get("sensors", {}).get("motion") or {}
    audio_data = (sensor_frame or {}).get("sensors", {}).get("audio") or {}
    raw_allowed = not bool(device["privacy_mode"])

    event = {
        "contract_version": "1.0.0",
        "event_id": f"event-{model_output['output_id']}",
        "device_id": model_input["device_id"],
        "timestamp_ms": model_input["timestamp_ms"],
        "sequence": int(sequence),
        "event_type": model_output["risk_type"],
        "priority": model_output["priority"],
        "source": "rule_router",
        "model_result": dict(model_output),
        "context": {
            "mode": model_input["mode"],
            "battery_percent": device["battery_percent"],
            "base_online": network["base_online"],
            "upload_available": network["upload_available"],
            "latitude_deg": location_data.get("latitude_deg"),
            "longitude_deg": location_data.get("longitude_deg"),
            "speed_mps": features["location"].get("speed_mps"),
        },
        "evidence": {
            "audio_clip_ref": audio_data.get("clip_ref") if raw_allowed else None,
            "image_ref": None,
            "imu_window_ref": motion_data.get("raw_ref") if raw_allowed else None,
            "location_fresh": model_input["evidence_available"]["fresh_gnss"],
        },
        "privacy": {
            "privacy_mode": device["privacy_mode"],
            "raw_evidence_allowed": raw_allowed,
            "retention_seconds": 3600 if raw_allowed else 0,
        },
    }
    if validate:
        validate_instance(event, load_schema("safety_event.schema.json"))
    return event
