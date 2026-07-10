"""Deterministic synthetic scenarios for contract and integration testing."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def base_model_input(input_id: str, *, mode: str = "personal_safety") -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "input_id": input_id,
        "device_id": "ego-link-sim-001",
        "timestamp_ms": 1_781_952_000_000,
        "mode": mode,
        "features": {
            "motion": {
                "activity_label": "walking",
                "activity_confidence": 0.9,
                "impact_score": 0.05,
                "fall_score": 0.03,
                "stationary_seconds": 0.0,
                "device_worn": True,
            },
            "audio": {
                "speech_score": 0.1,
                "distress_score": 0.02,
                "impact_sound_score": 0.03,
                "unknown_loud_sound_score": 0.02,
                "quality_score": 0.9,
            },
            "location": {
                "fix_valid": True,
                "speed_mps": 1.2,
                "outside_safe_zone": False,
                "dwell_seconds": 0.0,
                "route_deviation_m": 0.0,
                "quality_score": 0.9,
            },
            "network": {
                "connectivity_score": 0.85,
                "base_online": True,
                "upload_available": True,
                "signal_level": 3,
                "offline_seconds": 0.0,
            },
            "device": {
                "battery_percent": 78.0,
                "charging": False,
                "privacy_mode": False,
                "camera_available": True,
                "microphone_available": True,
            },
            "history": {
                "recent_risk_count_5m": 0,
                "last_user_response": "none",
                "seconds_since_last_contact": 20.0,
            },
            "user": {
                "sos_pressed": False,
                "cancel_pressed": False,
            },
        },
        "evidence_available": {
            "audio_clip": False,
            "single_image": False,
            "fresh_gnss": True,
            "imu_window": True,
        },
        "metadata": {"scenario": input_id},
    }


def build_scenario_suite() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    def add(
        scenario_id: str,
        description: str,
        changes: list[tuple[tuple[str, ...], Any]],
        *,
        expected_risk: str,
        expected_action: str,
        expected_priority: str,
        mode: str = "personal_safety",
        forbidden_evidence: list[str] | None = None,
    ) -> None:
        value = base_model_input(scenario_id, mode=mode)
        for path, replacement in changes:
            target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
        scenarios.append(
            {
                "id": scenario_id,
                "description": description,
                "input": value,
                "expected": {
                    "risk_type": expected_risk,
                    "recommended_action": expected_action,
                    "priority": expected_priority,
                    "forbidden_evidence": forbidden_evidence or [],
                },
            }
        )

    add(
        "normal_walk",
        "Normal walking with healthy device and network state.",
        [],
        expected_risk="none",
        expected_action="ignore",
        expected_priority="info",
    )
    add(
        "manual_sos",
        "User presses the physical SOS control.",
        [(('features', 'user', 'sos_pressed'), True)],
        expected_risk="manual_sos",
        expected_action="urgent_escalation",
        expected_priority="critical",
    )
    add(
        "post_impact_inactivity",
        "Strong impact followed by twenty seconds of inactivity.",
        [
            (('features', 'motion', 'activity_label'), 'impact'),
            (('features', 'motion', 'impact_score'), 0.92),
            (('features', 'motion', 'stationary_seconds'), 20.0),
            (('features', 'audio', 'impact_sound_score'), 0.76),
        ],
        expected_risk="post_impact_inactivity",
        expected_action="ask_user",
        expected_priority="high",
    )
    add(
        "post_impact_no_response",
        "Strong impact, long inactivity, and no response from the user.",
        [
            (('features', 'motion', 'activity_label'), 'impact'),
            (('features', 'motion', 'impact_score'), 0.95),
            (('features', 'motion', 'stationary_seconds'), 55.0),
            (('features', 'audio', 'impact_sound_score'), 0.82),
            (('features', 'history', 'last_user_response'), 'no_response'),
        ],
        expected_risk="post_impact_inactivity",
        expected_action="urgent_escalation",
        expected_priority="critical",
    )
    add(
        "possible_fall",
        "Motion model reports a high fall score without long inactivity yet.",
        [
            (('features', 'motion', 'activity_label'), 'fall_candidate'),
            (('features', 'motion', 'fall_score'), 0.91),
            (('features', 'motion', 'stationary_seconds'), 5.0),
        ],
        expected_risk="possible_fall",
        expected_action="ask_user",
        expected_priority="high",
    )
    add(
        "distress_audio",
        "Audio gate detects a strong distress signal.",
        [
            (('features', 'audio', 'speech_score'), 0.88),
            (('features', 'audio', 'distress_score'), 0.91),
        ],
        expected_risk="distress_audio",
        expected_action="ask_user",
        expected_priority="high",
    )
    add(
        "child_geofence",
        "Child safety mode remains outside a configured safe zone.",
        [
            (('features', 'location', 'outside_safe_zone'), True),
            (('features', 'location', 'dwell_seconds'), 180.0),
        ],
        expected_risk="geofence_exit",
        expected_action="ask_user",
        expected_priority="high",
        mode="child_safety",
    )
    add(
        "abnormal_dwell",
        "Device remains stationary at one location for an unusually long period.",
        [
            (('features', 'motion', 'activity_label'), 'stationary'),
            (('features', 'motion', 'activity_confidence'), 0.94),
            (('features', 'location', 'dwell_seconds'), 1200.0),
        ],
        expected_risk="abnormal_dwell",
        expected_action="send_summary",
        expected_priority="warning",
    )
    add(
        "communication_loss",
        "Device has remained offline and cannot reach the base.",
        [
            (('features', 'network', 'connectivity_score'), 0.0),
            (('features', 'network', 'base_online'), False),
            (('features', 'network', 'upload_available'), False),
            (('features', 'network', 'signal_level'), 0),
            (('features', 'network', 'offline_seconds'), 1200.0),
        ],
        expected_risk="communication_loss",
        expected_action="local_prompt",
        expected_priority="high",
    )
    add(
        "low_battery",
        "Battery falls below the warning threshold while the link is still available.",
        [(('features', 'device', 'battery_percent'), 9.0)],
        expected_risk="low_battery",
        expected_action="send_summary",
        expected_priority="warning",
    )
    add(
        "ambiguous_loud_event",
        "Uncertain loud event should request more evidence rather than escalate.",
        [(('features', 'audio', 'unknown_loud_sound_score'), 0.66)],
        expected_risk="uncertain",
        expected_action="capture_more",
        expected_priority="warning",
    )
    add(
        "privacy_restricted_impact",
        "Impact event in privacy mode must not request raw audio or image evidence.",
        [
            (('features', 'motion', 'activity_label'), 'impact'),
            (('features', 'motion', 'impact_score'), 0.93),
            (('features', 'motion', 'stationary_seconds'), 22.0),
            (('features', 'audio', 'impact_sound_score'), 0.80),
            (('features', 'device', 'privacy_mode'), True),
        ],
        expected_risk="post_impact_inactivity",
        expected_action="ask_user",
        expected_priority="high",
        forbidden_evidence=["audio_5s", "image_single"],
    )
    return scenarios


def sample_sensor_frames() -> list[dict[str, Any]]:
    common_device = {
        "battery_percent": 76.0,
        "charging": False,
        "temperature_c": 31.5,
        "privacy_mode": False,
        "camera_available": True,
        "microphone_available": True,
    }
    common_network = {
        "registered": True,
        "link_type": "wifi_mock",
        "rssi_dbm": -58,
        "signal_level": 3,
        "round_trip_ms": 42.0,
        "upload_available": True,
        "base_online": True,
        "offline_seconds": 0.0,
    }
    return [
        {
            "contract_version": "1.0.0",
            "frame_id": "frame-normal-001",
            "device_id": "ego-link-sim-001",
            "timestamp_ms": 1_781_952_000_000,
            "monotonic_ms": 1000,
            "sequence": 1,
            "mode": "personal_safety",
            "source": "simulator",
            "sensors": {
                "motion": {
                    "sample_rate_hz": 50.0,
                    "window_duration_ms": 2560,
                    "accel_mps2": None,
                    "gyro_rad_s": None,
                    "summary": {
                        "activity_label": "walking",
                        "activity_confidence": 0.92,
                        "max_accel_g": 1.3,
                        "jerk_peak_g_s": 3.2,
                        "orientation_change_deg": 8.0,
                        "impact_score": 0.04,
                        "fall_score": 0.03,
                        "stationary_seconds": 0.0,
                        "device_worn": True,
                    },
                    "raw_ref": None,
                },
                "audio": {
                    "sample_rate_hz": 16000,
                    "window_duration_ms": 1000,
                    "vad_probability": 0.1,
                    "rms_dbfs": -48.0,
                    "peak_dbfs": -31.0,
                    "quality_score": 0.88,
                    "event_scores": {"speech": 0.1, "distress": 0.02, "impact": 0.02, "unknown_loud_sound": 0.02},
                    "clip_ref": None,
                },
                "location": {
                    "fix_valid": True,
                    "latitude_deg": 22.543096,
                    "longitude_deg": 114.057865,
                    "speed_mps": 1.2,
                    "heading_deg": 95.0,
                    "accuracy_m": 7.0,
                    "fix_age_ms": 1000,
                    "outside_safe_zone": False,
                    "dwell_seconds": 0.0,
                    "route_deviation_m": 0.0,
                    "quality_score": 0.9,
                },
                "network": deepcopy(common_network),
                "device": deepcopy(common_device),
                "user_input": {"sos_pressed": False, "cancel_pressed": False, "response": "none"},
            },
            "metadata": {"scenario": "normal_walk"},
        },
        {
            "contract_version": "1.0.0",
            "frame_id": "frame-sos-001",
            "device_id": "ego-link-sim-001",
            "timestamp_ms": 1_781_952_010_000,
            "monotonic_ms": 11000,
            "sequence": 2,
            "mode": "personal_safety",
            "source": "simulator",
            "sensors": {
                "motion": None,
                "audio": None,
                "location": {
                    "fix_valid": True,
                    "latitude_deg": 22.543096,
                    "longitude_deg": 114.057865,
                    "speed_mps": 0.0,
                    "heading_deg": None,
                    "accuracy_m": 8.0,
                    "fix_age_ms": 5000,
                    "outside_safe_zone": False,
                    "dwell_seconds": 30.0,
                    "route_deviation_m": 0.0,
                    "quality_score": 0.85,
                },
                "network": deepcopy(common_network),
                "device": deepcopy(common_device),
                "user_input": {"sos_pressed": True, "cancel_pressed": False, "response": "need_help"},
            },
            "metadata": {"scenario": "manual_sos"},
        },
    ]
