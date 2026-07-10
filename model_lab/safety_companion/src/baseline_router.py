"""Deterministic Safety Companion M0 router.

The rule baseline is intentionally transparent. It defines the behavior and
contracts that later MotionNet, AudioGate, and learned ContextRouter models must
match or improve upon. It is not a medical or emergency diagnosis system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .contract_validation import load_schema, validate_instance


@dataclass(frozen=True)
class RouterConfig:
    model_name: str
    model_version: str
    thresholds: dict[str, float]
    weights: dict[str, float]
    defaults: dict[str, float]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RouterConfig":
        return cls(
            model_name=str(value["model_name"]),
            model_version=str(value["model_version"]),
            thresholds={key: float(item) for key, item in value["thresholds"].items()},
            weights={key: float(item) for key, item in value["weights"].items()},
            defaults={key: float(item) for key, item in value["defaults"].items()},
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "RouterConfig":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_mapping(json.load(handle))

    @classmethod
    def default(cls) -> "RouterConfig":
        path = Path(__file__).resolve().parents[1] / "configs" / "router_v0.1.0.json"
        return cls.from_file(path)


class RuleRouter:
    """Reference decision engine for the P0 safety companion scenario."""

    def __init__(self, config: RouterConfig | None = None, *, validate_contracts: bool = True):
        self.config = config or RouterConfig.default()
        self.validate_contracts = validate_contracts

    def evaluate(self, model_input: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(model_input)
        if self.validate_contracts:
            validate_instance(value, load_schema("model_input.schema.json"))

        features = value["features"]
        motion = features["motion"]
        audio = features["audio"]
        location = features["location"]
        network = features["network"]
        device = features["device"]
        history = features["history"]
        user = features["user"]
        t = self.config.thresholds
        w = self.config.weights

        if user["cancel_pressed"] and not user["sos_pressed"]:
            result = self._result(
                value,
                risk_type="none",
                risk_score=0.0,
                confidence=1.0,
                priority="info",
                action="ignore",
                requires_base=False,
                evidence_request=[],
                reason_codes=["user_cancelled"],
                safety_rule_applied=True,
            )
            return self._validated(result)

        if user["sos_pressed"]:
            result = self._result(
                value,
                risk_type="manual_sos",
                risk_score=t["manual_sos_score"],
                confidence=1.0,
                priority="critical",
                action="urgent_escalation",
                requires_base=True,
                evidence_request=["gnss_refresh", "user_confirmation"],
                reason_codes=["manual_sos_pressed", "deterministic_safety_override"],
                safety_rule_applied=True,
            )
            return self._validated(self._apply_evidence_policy(result, device))

        impact = max(float(motion["impact_score"]), 0.85 * float(audio["impact_sound_score"]))
        fall = float(motion["fall_score"])
        stationary = float(motion["stationary_seconds"])
        distress = float(audio["distress_score"])
        no_response = history["last_user_response"] == "no_response"

        if impact >= t["impact_high"] and stationary >= t["post_impact_stationary_seconds"]:
            stationary_factor = min(1.0, stationary / max(1.0, t["post_impact_urgent_seconds"]))
            risk = _clamp(
                w["post_impact_motion"] * impact
                + w["post_impact_audio"] * float(audio["impact_sound_score"])
                + w["post_impact_stationary"] * stationary_factor
                + w["post_impact_no_response"] * float(no_response)
            )
            urgent = stationary >= t["post_impact_urgent_seconds"] or no_response
            result = self._result(
                value,
                risk_type="post_impact_inactivity",
                risk_score=risk,
                confidence=max(impact, stationary_factor),
                priority="critical" if urgent else "high",
                action="urgent_escalation" if urgent else "ask_user",
                requires_base=True,
                evidence_request=["user_confirmation", "gnss_refresh", "imu_10s", "audio_5s", "image_single"],
                reason_codes=["impact_detected", "post_impact_stationary"] + (["user_no_response"] if no_response else []),
                safety_rule_applied=urgent,
                debug={"combined_impact": impact, "stationary_factor": stationary_factor},
            )
            return self._validated(self._apply_evidence_policy(result, device))

        if fall >= t["fall_high"]:
            stationary_factor = min(1.0, stationary / max(1.0, t["post_impact_stationary_seconds"]))
            risk = _clamp(
                w["fall_motion"] * fall
                + w["fall_stationary"] * stationary_factor
                + w["fall_audio"] * float(audio["impact_sound_score"])
            )
            result = self._result(
                value,
                risk_type="possible_fall",
                risk_score=risk,
                confidence=fall,
                priority="high",
                action="ask_user",
                requires_base=True,
                evidence_request=["user_confirmation", "gnss_refresh", "imu_10s", "audio_5s"],
                reason_codes=["fall_score_high"],
                safety_rule_applied=False,
                debug={"stationary_factor": stationary_factor},
            )
            return self._validated(self._apply_evidence_policy(result, device))

        if distress >= t["distress_high"]:
            motion_support = max(impact, fall)
            context_support = 1.0 if history["last_user_response"] in {"need_help", "no_response"} else 0.0
            risk = _clamp(
                w["distress_audio"] * distress
                + w["distress_motion"] * motion_support
                + w["distress_context"] * context_support
            )
            urgent = history["last_user_response"] == "need_help"
            result = self._result(
                value,
                risk_type="distress_audio",
                risk_score=risk,
                confidence=distress,
                priority="critical" if urgent else "high",
                action="urgent_escalation" if urgent else "ask_user",
                requires_base=True,
                evidence_request=["user_confirmation", "audio_5s", "gnss_refresh"],
                reason_codes=["distress_audio_high"] + (["help_confirmed"] if urgent else []),
                safety_rule_applied=urgent,
            )
            return self._validated(self._apply_evidence_policy(result, device))

        if bool(location["outside_safe_zone"]) and float(location["dwell_seconds"]) >= t["geofence_dwell_seconds"]:
            risk = _clamp(0.65 + min(0.25, float(location["dwell_seconds"]) / 3600.0))
            result = self._result(
                value,
                risk_type="geofence_exit",
                risk_score=risk,
                confidence=float(location["quality_score"]),
                priority="high" if value["mode"] in {"child_safety", "elder_safety"} else "warning",
                action="ask_user",
                requires_base=True,
                evidence_request=["user_confirmation", "gnss_refresh"],
                reason_codes=["outside_safe_zone", "geofence_dwell_exceeded"],
                safety_rule_applied=False,
            )
            return self._validated(self._apply_evidence_policy(result, device))

        if (
            motion["activity_label"] == "stationary"
            and float(location["dwell_seconds"]) >= t["abnormal_dwell_seconds"]
        ):
            result = self._result(
                value,
                risk_type="abnormal_dwell",
                risk_score=0.62,
                confidence=max(float(motion["activity_confidence"]), float(location["quality_score"])),
                priority="warning",
                action="send_summary",
                requires_base=True,
                evidence_request=["gnss_refresh"],
                reason_codes=["long_stationary_dwell"],
                safety_rule_applied=False,
            )
            return self._validated(result)

        offline_seconds = float(network["offline_seconds"])
        if offline_seconds >= t["network_offline_warning_seconds"]:
            high = offline_seconds >= t["network_offline_high_seconds"]
            result = self._result(
                value,
                risk_type="communication_loss",
                risk_score=0.85 if high else 0.58,
                confidence=1.0 - float(network["connectivity_score"]),
                priority="high" if high else "warning",
                action="local_prompt",
                requires_base=False,
                evidence_request=[],
                reason_codes=["network_offline", "base_unreachable"] if not network["base_online"] else ["network_offline"],
                safety_rule_applied=high,
            )
            return self._validated(result)

        battery = float(device["battery_percent"])
        if battery <= t["low_battery_warning_percent"] and not device["charging"]:
            critical = battery <= t["low_battery_critical_percent"]
            result = self._result(
                value,
                risk_type="low_battery",
                risk_score=0.95 if critical else 0.55,
                confidence=1.0,
                priority="critical" if critical else "warning",
                action="send_summary" if network["upload_available"] else "local_prompt",
                requires_base=bool(network["upload_available"]),
                evidence_request=[],
                reason_codes=["battery_critical" if critical else "battery_low"],
                safety_rule_applied=critical,
            )
            return self._validated(result)

        ambiguous_score = max(impact, fall, distress, float(audio["unknown_loud_sound_score"]))
        if ambiguous_score >= t["uncertainty_capture_threshold"]:
            result = self._result(
                value,
                risk_type="uncertain",
                risk_score=ambiguous_score,
                confidence=ambiguous_score,
                priority="warning",
                action="capture_more",
                requires_base=False,
                evidence_request=["imu_10s", "audio_5s", "gnss_refresh"],
                reason_codes=["ambiguous_signal_requires_more_evidence"],
                safety_rule_applied=False,
            )
            return self._validated(self._apply_evidence_policy(result, device))

        result = self._result(
            value,
            risk_type="none",
            risk_score=0.0,
            confidence=max(0.5, 1.0 - ambiguous_score),
            priority="info",
            action="ignore",
            requires_base=False,
            evidence_request=[],
            reason_codes=["no_safety_risk_detected"],
            safety_rule_applied=False,
        )
        return self._validated(result)

    def _result(
        self,
        value: Mapping[str, Any],
        *,
        risk_type: str,
        risk_score: float,
        confidence: float,
        priority: str,
        action: str,
        requires_base: bool,
        evidence_request: list[str],
        reason_codes: list[str],
        safety_rule_applied: bool,
        debug: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "contract_version": "1.0.0",
            "output_id": f"output-{value['input_id']}",
            "input_id": value["input_id"],
            "model_name": self.config.model_name,
            "model_version": self.config.model_version,
            "risk_type": risk_type,
            "risk_score": round(_clamp(risk_score), 6),
            "confidence": round(_clamp(confidence), 6),
            "priority": priority,
            "recommended_action": action,
            "requires_base": requires_base,
            "evidence_request": list(dict.fromkeys(evidence_request)),
            "reason_codes": list(dict.fromkeys(reason_codes)),
            "safety_rule_applied": safety_rule_applied,
            "decision_ttl_ms": int(self.config.defaults["decision_ttl_ms"]),
        }
        if debug:
            result["debug"] = debug
        return result

    def _apply_evidence_policy(self, result: dict[str, Any], device: Mapping[str, Any]) -> dict[str, Any]:
        requested = list(result["evidence_request"])
        filtered: list[str] = []
        privacy_mode = bool(device["privacy_mode"])
        for item in requested:
            if item == "audio_5s" and (privacy_mode or not device["microphone_available"]):
                continue
            if item == "image_single" and (privacy_mode or not device["camera_available"]):
                continue
            filtered.append(item)
        result["evidence_request"] = filtered
        if privacy_mode and set(requested) != set(filtered):
            result["reason_codes"].append("privacy_restricted_raw_evidence")
        return result

    def _validated(self, result: dict[str, Any]) -> dict[str, Any]:
        if self.validate_contracts:
            validate_instance(result, load_schema("model_output.schema.json"))
        return result


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
