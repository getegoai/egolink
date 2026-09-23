"""Safety Kernel Arbitrator and Dual-Track Shadow Evaluator (AI-030).

Implements the arbitration mechanism defined in ADR-0017 and
AI_NATIVE_EGO_STATE_FLYWHEEL.md:
1. Dual-Track Execution: Deterministic Rule Engine + TinyML 1D-CNN.
2. Safety Kernel Absolute Priority: Physical SOS, confirmed falls, and power
   cutoffs have unconditional veto authority; AI inference cannot override.
3. Ambiguity & Discrepancy Mining: Automatically flags high-entropy windows
   and sensor contradictions as Gold Samples for the continuous learning flywheel.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from pc_simulator.tinyml_ego_state_model import (
    CLASS_NAMES,
    NUM_CLASSES,
    INPUT_LENGTH,
    INPUT_CHANNELS,
    TinyMLEgoStateModel,
    calculate_entropy,
)
from scripts.train_edge_tinyml_model import normalize_imu_tensor


# Entropy thresholds for uncertainty mining
DEFAULT_ENTROPY_HIGH_THRESHOLD = 1.20   # bits (bits > 1.20 indicates model confusion)
DEFAULT_CONFIDENCE_THRESHOLD = 0.65     # confidence >= 0.65 needed to trust model prediction


class SafetyKernelArbitrator:
    """Arbitrates between deterministic safety rules and TinyML edge predictions."""

    def __init__(
        self,
        tinyml_model: Optional[TinyMLEgoStateModel] = None,
        *,
        entropy_high_threshold: float = DEFAULT_ENTROPY_HIGH_THRESHOLD,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        self.model = tinyml_model if tinyml_model is not None else TinyMLEgoStateModel(seed=42)
        self.entropy_high_threshold = entropy_high_threshold
        self.confidence_threshold = confidence_threshold

    def evaluate_deterministic_rule(
        self,
        raw_tensor: np.ndarray,
        device_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate deterministic safety rules and physical sensor thresholds."""
        # 1. Critical Physical Overrides (Non-negotiable)
        if device_context.get("sos_button_pressed", False):
            return {
                "rule_state": "manual_sos",
                "priority": "critical",
                "is_critical_safety_override": True,
                "reason": "Physical SOS button pressed by user",
            }

        if device_context.get("battery_critical_cutoff", False):
            return {
                "rule_state": "critical_power_cutoff",
                "priority": "critical",
                "is_critical_safety_override": True,
                "reason": "Battery voltage dropped below emergency cutoff threshold",
            }

        # 2. IMU Physical Anomaly Detection
        # Check for high-G mechanical impact followed by immobility (fall pattern)
        accel_mags = np.linalg.norm(raw_tensor[:, :3], axis=1)  # [100]
        max_accel = float(np.max(accel_mags))
        tail_var = float(np.var(accel_mags[60:]))  # Variance in last 2 seconds

        if max_accel > 25.0 and tail_var < 0.20:
            return {
                "rule_state": "fall_suspected",
                "priority": "critical",
                "is_critical_safety_override": True,
                "reason": f"Impact spike ({max_accel:.1f} m/s^2) followed by immobility (var={tail_var:.3f})",
            }

        if max_accel > 28.0:
            return {
                "rule_state": "abnormal_shock",
                "priority": "warning",
                "is_critical_safety_override": False,
                "reason": f"High dynamic impact shock ({max_accel:.1f} m/s^2)",
            }

        # 3. Multi-Sensor Physical Invariants
        if device_context.get("is_charging", False) and np.var(raw_tensor[:, :3]) < 0.05:
            return {
                "rule_state": "stationary_charging",
                "priority": "info",
                "is_critical_safety_override": False,
                "reason": "Fuel gauge charging anchor confirmed with quiet IMU",
            }

        gnss_speed = device_context.get("gnss_speed_mps")
        gnss_fix = device_context.get("gnss_fix_type")
        if gnss_speed is not None and gnss_fix in ("3D", "2D"):
            # > 25 km/h (6.94 m/s)
            if gnss_speed >= 6.94:
                return {
                    "rule_state": "in_vehicle",
                    "priority": "info",
                    "is_critical_safety_override": False,
                    "reason": f"GNSS Doppler ground speed {gnss_speed * 3.6:.1f} km/h >= 25 km/h",
                }
            # 10 - 22 km/h (2.78 - 6.11 m/s)
            if 2.78 <= gnss_speed <= 6.11:
                return {
                    "rule_state": "cycling",
                    "priority": "info",
                    "is_critical_safety_override": False,
                    "reason": f"GNSS Doppler ground speed {gnss_speed * 3.6:.1f} km/h matches cycling regime",
                }

        # IMU mobility variance baseline
        imu_var = float(np.var(raw_tensor[:, :3]))
        if imu_var < 0.08:
            return {
                "rule_state": "stationary",
                "priority": "info",
                "is_critical_safety_override": False,
                "reason": f"IMU acceleration variance {imu_var:.4f} below stationary limit",
            }
        elif imu_var > 4.0:
            return {
                "rule_state": "running",
                "priority": "info",
                "is_critical_safety_override": False,
                "reason": f"IMU acceleration variance {imu_var:.4f} indicates high dynamic locomotion",
            }
        else:
            return {
                "rule_state": "walking",
                "priority": "info",
                "is_critical_safety_override": False,
                "reason": f"IMU acceleration variance {imu_var:.4f} indicates pedestrian cadence",
            }

    def arbitrate_window(
        self,
        raw_tensor_list: List[List[float]],
        device_context: Optional[Dict[str, Any]] = None,
        *,
        window_id: str = "win-sim",
    ) -> Dict[str, Any]:
        """Perform dual-track evaluation and Safety Kernel arbitration.

        Args:
            raw_tensor_list: Raw IMU readings [100, 6] in SI units (m/s^2, dps).
            device_context: Peripheral sensors and hardware status dictionary.
            window_id: Unique window identifier.

        Returns:
            Dictionary containing dual-track results, arbitrated decision,
            and flywheel gold sample flags.
        """
        if device_context is None:
            device_context = {}

        raw_tensor = np.array(raw_tensor_list, dtype=np.float32)
        norm_tensor = normalize_imu_tensor(raw_tensor_list)

        # 1. Deterministic Rule Engine Track
        rule_res = self.evaluate_deterministic_rule(raw_tensor, device_context)

        # 2. TinyML 1D-CNN Model Track
        model_pred = self.model.predict(norm_tensor)
        tinyml_state = model_pred["class_name"]
        tinyml_conf = model_pred["confidence"]
        tinyml_entropy = model_pred["entropy"]

        # 3. Arbitration Logic (Safety Kernel non-negotiable priority)
        is_safety_override = rule_res["is_critical_safety_override"]

        if is_safety_override:
            # Deterministic Safety Kernel vetoes AI completely
            arbitrated_state = rule_res["rule_state"]
            decision_source = "safety_kernel_override"
            arbitrated_priority = rule_res["priority"]
            arbitration_reason = f"Safety Kernel priority override: {rule_res['reason']}"
        else:
            # Normal operational regime: AI model enriches estimation if confident
            if tinyml_conf >= self.confidence_threshold and tinyml_entropy < self.entropy_high_threshold:
                arbitrated_state = tinyml_state
                decision_source = "tinyml_edge_model"
                arbitrated_priority = "info"
                arbitration_reason = f"TinyML confident inference (conf={tinyml_conf:.2f}, entropy={tinyml_entropy:.2f})"
            else:
                # Fallback to deterministic rule when AI is uncertain or low confidence
                arbitrated_state = rule_res["rule_state"]
                decision_source = "rule_fallback_uncertain_ai"
                arbitrated_priority = rule_res["priority"]
                arbitration_reason = f"Uncertain AI (entropy={tinyml_entropy:.2f}, conf={tinyml_conf:.2f}) -> Rule fallback"

        # 4. Ambiguity and Conflict Mining for Flywheel Retraining
        discrepancy = (rule_res["rule_state"] != tinyml_state)
        high_entropy = (tinyml_entropy >= self.entropy_high_threshold)

        # Cross-modal conflict check:
        # e.g., TinyML says running/walking, but GNSS Doppler speed is 0.0 with 3D fix
        gnss_speed = device_context.get("gnss_speed_mps")
        gnss_fix = device_context.get("gnss_fix_type")
        sensor_conflict = False
        conflict_desc = ""

        if gnss_fix in ("3D", "2D") and gnss_speed is not None:
            if tinyml_state in ("running", "cycling") and gnss_speed < 0.3:
                sensor_conflict = True
                conflict_desc = f"TinyML predicts '{tinyml_state}' but GNSS ground speed is {gnss_speed:.1f} m/s"
            elif tinyml_state == "stationary" and gnss_speed > 4.0:
                sensor_conflict = True
                conflict_desc = f"TinyML predicts 'stationary' but GNSS ground speed is {gnss_speed * 3.6:.1f} km/h"

        # Gold sample criteria: high uncertainty, sensor contradiction, or confident disagreement
        is_gold_sample = (
            high_entropy
            or sensor_conflict
            or (discrepancy and tinyml_conf >= 0.70 and not is_safety_override)
        )

        # Evidence digest for auditability
        digest_src = f"{window_id}:{arbitrated_state}:{tinyml_conf}:{tinyml_entropy}"
        evidence_digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()

        return {
            "window_id": window_id,
            "arbitrated_state": arbitrated_state,
            "decision_source": decision_source,
            "arbitrated_priority": arbitrated_priority,
            "arbitration_reason": arbitration_reason,
            "is_safety_override": is_safety_override,
            # Dual-track individual outputs
            "deterministic_rule": rule_res,
            "tinyml_inference": model_pred,
            # Flywheel data mining flags
            "discrepancy_flag": discrepancy,
            "high_entropy_flag": high_entropy,
            "sensor_conflict_flag": sensor_conflict,
            "conflict_description": conflict_desc,
            "is_gold_sample_for_flywheel": is_gold_sample,
            "evidence_digest": evidence_digest,
        }
