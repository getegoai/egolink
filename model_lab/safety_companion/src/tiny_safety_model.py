"""Tiny Safety Model v0 local reference implementation.

This module is intentionally small and dependency-free so the first deployable
shape can be exported to firmware later. It consumes the existing
`model_input` contract and predicts a coarse safety state. SOS/cancel handling
stays outside the model and must remain a deterministic Safety Kernel rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import random
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "egolink.tiny_safety_model.v0.1"
MODEL_NAME = "tiny_safety_model"
MODEL_VERSION = "0.1.0-synthetic-dry-run"
STATE_LABELS = ("normal", "uncertain", "needs_check", "possible_risk")
FEATURE_NAMES = (
    "motion_impact_score",
    "motion_fall_score",
    "motion_stationary_norm",
    "motion_activity_confidence",
    "motion_device_worn",
    "audio_distress_score",
    "audio_impact_sound_score",
    "audio_unknown_loud_sound_score",
    "location_outside_safe_zone",
    "location_dwell_norm",
    "network_connectivity_score",
    "network_offline_norm",
    "device_battery_low",
    "history_recent_risk_norm",
)


@dataclass(frozen=True)
class TinyPrediction:
    state_label: str
    class_index: int | None
    confidence: float
    scores: dict[str, float]
    safety_rule_required: bool
    reason_codes: list[str]


def clamp(value: Any, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def extract_features(model_input: Mapping[str, Any]) -> list[float]:
    """Extract bounded float features from the stable model_input contract."""

    features = as_dict(model_input.get("features"))
    motion = as_dict(features.get("motion"))
    audio = as_dict(features.get("audio"))
    location = as_dict(features.get("location"))
    network = as_dict(features.get("network"))
    device = as_dict(features.get("device"))
    history = as_dict(features.get("history"))
    return [
        clamp(motion.get("impact_score")),
        clamp(motion.get("fall_score")),
        clamp(float(motion.get("stationary_seconds") or 0.0) / 120.0),
        clamp(motion.get("activity_confidence")),
        1.0 if motion.get("device_worn") is True else 0.0,
        clamp(audio.get("distress_score")),
        clamp(audio.get("impact_sound_score")),
        clamp(audio.get("unknown_loud_sound_score")),
        1.0 if location.get("outside_safe_zone") else 0.0,
        clamp(float(location.get("dwell_seconds") or 0.0) / 1800.0),
        clamp(network.get("connectivity_score")),
        clamp(float(network.get("offline_seconds") or 0.0) / 1800.0),
        clamp((100.0 - float(device.get("battery_percent") or 100.0)) / 100.0),
        clamp(float(history.get("recent_risk_count_5m") or 0.0) / 5.0),
    ]


def user_override_required(model_input: Mapping[str, Any]) -> bool:
    user = as_dict(as_dict(model_input.get("features")).get("user"))
    return bool(user.get("sos_pressed") or user.get("cancel_pressed"))


def train_linear_centroid_model(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Train a tiny linear classifier from feature rows.

    The model compares class centroids using a linearized squared-distance
    score: `2 * centroid dot x - ||centroid||^2 + log(prior)`.
    """

    if not rows:
        raise ValueError("training rows are required")
    grouped: dict[str, list[list[float]]] = {label: [] for label in STATE_LABELS}
    for row in rows:
        label = str(row.get("label") or "")
        if label not in grouped:
            raise ValueError(f"unknown label: {label}")
        values = [clamp(value) for value in row.get("features") or []]
        if len(values) != len(FEATURE_NAMES):
            raise ValueError(f"expected {len(FEATURE_NAMES)} features, got {len(values)}")
        grouped[label].append(values)

    total = sum(len(items) for items in grouped.values())
    weights: list[list[float]] = []
    biases: list[float] = []
    centroids: dict[str, list[float]] = {}
    for label in STATE_LABELS:
        items = grouped[label]
        if not items:
            raise ValueError(f"no rows for label: {label}")
        centroid = [sum(row[index] for row in items) / len(items) for index in range(len(FEATURE_NAMES))]
        prior = len(items) / total
        centroids[label] = [round(value, 6) for value in centroid]
        weights.append([round(2.0 * value, 6) for value in centroid])
        biases.append(round(-sum(value * value for value in centroid) + math.log(prior), 6))

    return {
        "feature_names": list(FEATURE_NAMES),
        "state_labels": list(STATE_LABELS),
        "centroids": centroids,
        "weights": weights,
        "biases": biases,
        "score_type": "linearized_nearest_centroid",
    }


def predict(model_input: Mapping[str, Any], artifact: Mapping[str, Any]) -> TinyPrediction:
    if user_override_required(model_input):
        return TinyPrediction(
            state_label="safety_rule_required",
            class_index=None,
            confidence=1.0,
            scores={},
            safety_rule_required=True,
            reason_codes=["sos_or_cancel_must_be_handled_by_safety_kernel"],
        )

    features = extract_features(model_input)
    linear = as_dict(artifact.get("linear_model"))
    labels = [str(label) for label in linear.get("state_labels") or STATE_LABELS]
    weights = linear.get("weights") or []
    biases = linear.get("biases") or []
    if len(weights) != len(labels) or len(biases) != len(labels):
        raise ValueError("artifact linear_model dimensions do not match state labels")

    raw_scores: list[float] = []
    for class_index, label in enumerate(labels):
        class_weights = weights[class_index]
        if len(class_weights) != len(features):
            raise ValueError(f"artifact weights for {label} do not match feature count")
        raw_scores.append(float(biases[class_index]) + sum(float(w) * x for w, x in zip(class_weights, features)))

    probabilities = softmax(raw_scores)
    best_index = max(range(len(labels)), key=lambda index: probabilities[index])
    scores = {labels[index]: round(probabilities[index], 6) for index in range(len(labels))}
    return TinyPrediction(
        state_label=labels[best_index],
        class_index=best_index,
        confidence=round(probabilities[best_index], 6),
        scores=scores,
        safety_rule_required=False,
        reason_codes=["tiny_safety_model_v0_synthetic_reference"],
    )


def softmax(scores: Sequence[float]) -> list[float]:
    peak = max(scores)
    values = [math.exp(score - peak) for score in scores]
    total = sum(values)
    return [value / total for value in values]


def synthetic_training_rows(*, samples_per_class: int = 24, seed: int = 7) -> list[dict[str, Any]]:
    if samples_per_class <= 0:
        raise ValueError("samples_per_class must be positive")
    rng = random.Random(seed)
    templates = {
        "normal": {
            "motion_impact_score": 0.05,
            "motion_fall_score": 0.03,
            "motion_stationary_norm": 0.05,
            "motion_activity_confidence": 0.85,
            "motion_device_worn": 1.0,
            "audio_distress_score": 0.02,
            "audio_impact_sound_score": 0.02,
            "audio_unknown_loud_sound_score": 0.05,
            "location_outside_safe_zone": 0.0,
            "location_dwell_norm": 0.05,
            "network_connectivity_score": 0.85,
            "network_offline_norm": 0.0,
            "device_battery_low": 0.15,
            "history_recent_risk_norm": 0.0,
        },
        "uncertain": {
            "motion_impact_score": 0.32,
            "motion_fall_score": 0.24,
            "motion_stationary_norm": 0.18,
            "motion_activity_confidence": 0.55,
            "motion_device_worn": 1.0,
            "audio_distress_score": 0.25,
            "audio_impact_sound_score": 0.22,
            "audio_unknown_loud_sound_score": 0.46,
            "location_outside_safe_zone": 0.0,
            "location_dwell_norm": 0.12,
            "network_connectivity_score": 0.65,
            "network_offline_norm": 0.1,
            "device_battery_low": 0.2,
            "history_recent_risk_norm": 0.15,
        },
        "needs_check": {
            "motion_impact_score": 0.52,
            "motion_fall_score": 0.58,
            "motion_stationary_norm": 0.32,
            "motion_activity_confidence": 0.72,
            "motion_device_worn": 1.0,
            "audio_distress_score": 0.32,
            "audio_impact_sound_score": 0.42,
            "audio_unknown_loud_sound_score": 0.25,
            "location_outside_safe_zone": 0.2,
            "location_dwell_norm": 0.2,
            "network_connectivity_score": 0.55,
            "network_offline_norm": 0.18,
            "device_battery_low": 0.25,
            "history_recent_risk_norm": 0.25,
        },
        "possible_risk": {
            "motion_impact_score": 0.88,
            "motion_fall_score": 0.82,
            "motion_stationary_norm": 0.74,
            "motion_activity_confidence": 0.88,
            "motion_device_worn": 1.0,
            "audio_distress_score": 0.62,
            "audio_impact_sound_score": 0.72,
            "audio_unknown_loud_sound_score": 0.3,
            "location_outside_safe_zone": 0.35,
            "location_dwell_norm": 0.28,
            "network_connectivity_score": 0.45,
            "network_offline_norm": 0.24,
            "device_battery_low": 0.32,
            "history_recent_risk_norm": 0.35,
        },
    }
    rows: list[dict[str, Any]] = []
    for label in STATE_LABELS:
        base = templates[label]
        for index in range(samples_per_class):
            features = []
            for name in FEATURE_NAMES:
                jitter = rng.uniform(-0.05, 0.05)
                if name in {"location_outside_safe_zone", "motion_device_worn"}:
                    jitter = rng.uniform(-0.02, 0.02)
                features.append(round(clamp(base[name] + jitter), 6))
            rows.append(
                {
                    "row_id": f"synthetic-{label}-{index:03d}",
                    "label": label,
                    "features": features,
                    "synthetic_only": True,
                    "source": "model-device-001-synthetic-template",
                }
            )
    return rows


def evaluate_rows(rows: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any]) -> dict[str, Any]:
    if not rows:
        return {"row_count": 0, "accuracy": 0.0, "by_label": {}}
    correct = 0
    by_label: dict[str, Counter[str]] = {label: Counter() for label in STATE_LABELS}
    for row in rows:
        prediction = predict(model_input_from_feature_row(row), artifact)
        label = str(row["label"])
        by_label.setdefault(label, Counter())[prediction.state_label] += 1
        if prediction.state_label == label:
            correct += 1
    return {
        "row_count": len(rows),
        "accuracy": round(correct / len(rows), 6),
        "by_label": {label: dict(counter) for label, counter in by_label.items()},
    }


def model_input_from_feature_row(row: Mapping[str, Any]) -> dict[str, Any]:
    values = list(row.get("features") or [])
    lookup = {name: values[index] for index, name in enumerate(FEATURE_NAMES)}
    return {
        "contract_version": "1.0.0",
        "input_id": f"input-{row.get('row_id', 'synthetic')}",
        "device_id": "synthetic-device",
        "timestamp_ms": 0,
        "mode": "test",
        "features": {
            "motion": {
                "activity_label": "unknown",
                "activity_confidence": lookup["motion_activity_confidence"],
                "impact_score": lookup["motion_impact_score"],
                "fall_score": lookup["motion_fall_score"],
                "stationary_seconds": lookup["motion_stationary_norm"] * 120.0,
                "device_worn": bool(lookup["motion_device_worn"] >= 0.5),
            },
            "audio": {
                "speech_score": 0.0,
                "distress_score": lookup["audio_distress_score"],
                "impact_sound_score": lookup["audio_impact_sound_score"],
                "unknown_loud_sound_score": lookup["audio_unknown_loud_sound_score"],
                "quality_score": 1.0,
            },
            "location": {
                "fix_valid": True,
                "speed_mps": 0.0,
                "outside_safe_zone": bool(lookup["location_outside_safe_zone"] >= 0.5),
                "dwell_seconds": lookup["location_dwell_norm"] * 1800.0,
                "route_deviation_m": 0.0,
                "quality_score": 0.8,
            },
            "network": {
                "connectivity_score": lookup["network_connectivity_score"],
                "base_online": True,
                "upload_available": True,
                "signal_level": 4,
                "offline_seconds": lookup["network_offline_norm"] * 1800.0,
            },
            "device": {
                "battery_percent": 100.0 - lookup["device_battery_low"] * 100.0,
                "charging": False,
                "privacy_mode": False,
                "camera_available": False,
                "microphone_available": False,
            },
            "history": {
                "recent_risk_count_5m": int(round(lookup["history_recent_risk_norm"] * 5.0)),
                "last_user_response": "none",
                "seconds_since_last_contact": 0.0,
            },
            "user": {"sos_pressed": False, "cancel_pressed": False},
        },
        "evidence_available": {
            "audio_clip": False,
            "single_image": False,
            "fresh_gnss": True,
            "imu_window": True,
        },
        "metadata": {"synthetic_only": True},
    }


def build_artifact(
    *,
    model_id: str,
    generated_at: str,
    training_rows: Sequence[Mapping[str, Any]],
    holdout_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    linear_model = train_linear_centroid_model(training_rows)
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "model_id": model_id,
        "generated_at": generated_at,
        "serves_demo": "D4-D5",
        "model_type": "linearized_centroid_classifier",
        "input_contract": "shared/contracts/model_input.schema.json",
        "output_state_labels": list(STATE_LABELS),
        "linear_model": linear_model,
        "training_data": {
            "synthetic_only": True,
            "source": "deterministic_templates",
            "training_rows": len(training_rows),
            "holdout_rows": len(holdout_rows),
            "real_field_rows": 0,
            "private_rows": 0,
        },
        "metrics": {
            "training": evaluate_rows(training_rows, {"linear_model": linear_model}),
            "holdout": evaluate_rows(holdout_rows, {"linear_model": linear_model}),
            "metric_scope": "synthetic_integration_only",
        },
        "deployment": {
            "export_format": "c_header_ready",
            "firmware_integrated": False,
            "device_deployed": False,
            "measured_latency_ms": None,
            "measured_ram_bytes": None,
            "measured_flash_bytes": None,
            "measured_power_mw": None,
        },
        "safety": {
            "sos_cancel_handled_by_safety_kernel": True,
            "model_controls_external_actions": False,
            "real_emergency_escalation_allowed": False,
            "release_claim_allowed": False,
        },
        "test_vectors": build_test_vectors(linear_model),
        "non_claims": non_claims(),
    }
    return artifact


def build_test_vectors(linear_model: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = synthetic_training_rows(samples_per_class=1, seed=101)
    artifact = {"linear_model": linear_model}
    vectors: list[dict[str, Any]] = []
    for row in rows:
        prediction = predict(model_input_from_feature_row(row), artifact)
        vectors.append(
            {
                "id": row["row_id"],
                "features": row["features"],
                "expected_label": row["label"],
                "predicted_label": prediction.state_label,
                "confidence": prediction.confidence,
                "synthetic_only": True,
            }
        )
    return vectors


def non_claims() -> list[str]:
    return [
        "Synthetic integration model only; no real-world accuracy is claimed.",
        "The model does not replace deterministic SOS, cancel, privacy, power, or escalation rules.",
        "No firmware integration, device deployment, latency, RAM, flash, or power measurement is claimed.",
        "No private field samples or candidate DB rows are read by this artifact.",
    ]


def split_rows(rows: Sequence[dict[str, Any]], *, holdout_stride: int = 4) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    training: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index % holdout_stride == holdout_stride - 1:
            holdout.append(row)
        else:
            training.append(row)
    return training, holdout
