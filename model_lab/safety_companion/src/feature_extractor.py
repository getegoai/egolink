"""Convert a versioned sensor frame into the stable router input contract."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .contract_validation import load_schema, validate_instance


def build_model_input(
    sensor_frame: Mapping[str, Any],
    *,
    history: Mapping[str, Any] | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Build a normalized safety router input.

    The function accepts sparse P0 frames. Missing sensors become neutral values,
    which lets firmware mocks and the PC simulator share the same interface.
    """

    frame = deepcopy(dict(sensor_frame))
    if validate:
        validate_instance(frame, load_schema("sensor_frame.schema.json"))

    sensors = frame.get("sensors", {})
    motion = sensors.get("motion") or {}
    motion_summary = motion.get("summary") or {}
    audio = sensors.get("audio") or {}
    audio_scores = audio.get("event_scores") or {}
    location = sensors.get("location") or {}
    network = sensors.get("network") or {}
    device = sensors.get("device") or {}
    user_input = sensors.get("user_input") or {}
    history_values = {
        "recent_risk_count_5m": 0,
        "last_user_response": user_input.get("response", "none"),
        "seconds_since_last_contact": 0.0,
    }
    if history:
        history_values.update(dict(history))

    connectivity_score = _connectivity_score(network)
    model_input: dict[str, Any] = {
        "contract_version": "1.0.0",
        "input_id": f"input-{frame['frame_id']}",
        "device_id": frame["device_id"],
        "timestamp_ms": frame["timestamp_ms"],
        "mode": frame["mode"],
        "features": {
            "motion": {
                "activity_label": motion_summary.get("activity_label", "unknown"),
                "activity_confidence": float(motion_summary.get("activity_confidence", 0.0)),
                "impact_score": float(motion_summary.get("impact_score", 0.0)),
                "fall_score": float(motion_summary.get("fall_score", 0.0)),
                "stationary_seconds": float(motion_summary.get("stationary_seconds", 0.0)),
                "device_worn": motion_summary.get("device_worn"),
            },
            "audio": {
                "speech_score": float(audio_scores.get("speech", 0.0)),
                "distress_score": float(audio_scores.get("distress", 0.0)),
                "impact_sound_score": float(audio_scores.get("impact", 0.0)),
                "unknown_loud_sound_score": float(audio_scores.get("unknown_loud_sound", 0.0)),
                "quality_score": float(audio.get("quality_score", 0.0)),
            },
            "location": {
                "fix_valid": bool(location.get("fix_valid", False)),
                "speed_mps": float(location.get("speed_mps", 0.0)),
                "outside_safe_zone": bool(location.get("outside_safe_zone", False)),
                "dwell_seconds": float(location.get("dwell_seconds", 0.0)),
                "route_deviation_m": float(location.get("route_deviation_m", 0.0)),
                "quality_score": float(location.get("quality_score", 0.0)),
            },
            "network": {
                "connectivity_score": connectivity_score,
                "base_online": bool(network.get("base_online", False)),
                "upload_available": bool(network.get("upload_available", False)),
                "signal_level": int(network.get("signal_level", 0)),
                "offline_seconds": float(network.get("offline_seconds", 0.0)),
            },
            "device": {
                "battery_percent": float(device.get("battery_percent", 100.0)),
                "charging": bool(device.get("charging", False)),
                "privacy_mode": bool(device.get("privacy_mode", False)),
                "camera_available": bool(device.get("camera_available", False)),
                "microphone_available": bool(device.get("microphone_available", False)),
            },
            "history": {
                "recent_risk_count_5m": int(history_values["recent_risk_count_5m"]),
                "last_user_response": str(history_values["last_user_response"]),
                "seconds_since_last_contact": float(history_values["seconds_since_last_contact"]),
            },
            "user": {
                "sos_pressed": bool(user_input.get("sos_pressed", False)),
                "cancel_pressed": bool(user_input.get("cancel_pressed", False)),
            },
        },
        "evidence_available": {
            "audio_clip": bool(audio.get("clip_ref")),
            "single_image": False,
            "fresh_gnss": bool(location.get("fix_valid", False)) and int(location.get("fix_age_ms") or 0) <= 30_000,
            "imu_window": bool(motion.get("raw_ref") or motion.get("accel_mps2")),
        },
        "metadata": {
            "source_frame_id": frame["frame_id"],
            "source": frame["source"],
            "sequence": frame["sequence"],
        },
    }

    if validate:
        validate_instance(model_input, load_schema("model_input.schema.json"))
    return model_input


def _connectivity_score(network: Mapping[str, Any]) -> float:
    if not network or not network.get("registered", False) or not network.get("upload_available", False):
        return 0.0
    signal_score = max(0.0, min(1.0, float(network.get("signal_level", 0)) / 4.0))
    rtt = network.get("round_trip_ms")
    if rtt is None:
        latency_score = 0.75
    else:
        latency_score = max(0.0, min(1.0, 1.0 - float(rtt) / 5000.0))
    return round(0.7 * signal_score + 0.3 * latency_score, 6)
