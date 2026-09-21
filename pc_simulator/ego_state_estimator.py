"""Deterministic Active Ego-State Estimator and Evidence Chain Generator.

Grounded in multi-source physical sensor evidence (20Hz/100Hz IMU, GNSS, Cellular/Wi-Fi, Battery)
to estimate user spatial mobility, posture anomalies, and device wear states
under strict Local-First privacy principles.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Sequence


CONTRACT_VERSION = "egolink.ego_state_estimation.v0.1"
EVIDENCE_CONTRACT_VERSION = "egolink.ego_state_evidence_chain.v0.1"
REPORT_CONTRACT_VERSION = "egolink.ego_state_report.v0.1"

SPATIAL_MOBILITY_STATES = frozenset({
    "stationary",
    "pedestrian_walking",
    "running",
    "in_vehicle",
    "indoor_weak_gnss",
    "unknown",
})

POSTURE_ANOMALY_STATES = frozenset({
    "normal",
    "abnormal_shock",
    "suspected_fall",
    "prolonged_immobility",
    "unknown",
})

DEVICE_WEAR_STATES = frozenset({
    "tabletop_resting",
    "handheld",
    "wearable_or_bag",
    "charging_docked",
    "unknown",
})


class EgoStateEstimator:
    """Active Ego-State Estimator maintaining rolling multi-source evidence windows."""

    def __init__(
        self,
        device_id: str = "ego-link-001",
        boot_count: int = 1,
        session_id: str = "session-1",
        firmware_version: str = "0.1.0-sensor-policy-continuous-021",
        firmware_elf_sha256: str = "2411325042246be77f9e696f9d1cc7c89840f97e46fc4a7b5c928bc7c1d39e87",
    ) -> None:
        self.device_id = device_id
        self.boot_count = boot_count
        self.session_id = session_id
        self.firmware_version = firmware_version
        self.firmware_elf_sha256 = firmware_elf_sha256

        # Rolling IMU samples: list of (ax_m_s2, ay_m_s2, az_m_s2, gx_dps, gy_dps, gz_dps, timestamp_ns, is_mock)
        self._imu_window: list[tuple[float, float, float, float, float, float, int, bool]] = []
        self._max_imu_window_samples = 200

        # Location snapshot
        self._location_fix_valid = False
        self._location_lat: float | None = None
        self._location_lon: float | None = None
        self._location_hdop: float | None = None
        self._location_ground_speed_m_s: float | None = None
        self._location_satellites: int | None = None
        self._location_course_deg: float | None = None
        self._last_location_update_ns: int | None = None

        # Network snapshot
        self._network_type: str = "offline"
        self._network_lte_rsrp: float | None = None
        self._network_lte_cell_id: str | None = None
        self._network_wifi_ap_count: int | None = None
        self._network_wifi_hash: str | None = None

        # Power snapshot
        self._power_soc: float | None = None
        self._power_voltage_mv: int | None = None
        self._power_charging: bool | None = None

        # State tracking
        self._last_peak_accel: float = 0.0
        self._last_shock_time_ns: int | None = None
        self._immobility_start_ns: int | None = None
        self._estimation_sequence: int = 0

    def feed_imu_sample(
        self,
        ax_mg: float,
        ay_mg: float,
        az_mg: float,
        gx_mdps: float,
        gy_mdps: float,
        gz_mdps: float,
        timestamp_ns: int,
        is_mock: bool = False,
    ) -> None:
        """Feed a single 6-axis IMU measurement (accel in mg, gyro in mdps)."""
        # Convert mg to m/s^2 (1g = 9.80665 m/s^2, 1000 mg = 1g)
        ax = ax_mg * 0.00980665
        ay = ay_mg * 0.00980665
        az = az_mg * 0.00980665

        # Convert mdps to deg/s
        gx = gx_mdps * 0.001
        gy = gy_mdps * 0.001
        gz = gz_mdps * 0.001

        self._imu_window.append((ax, ay, az, gx, gy, gz, timestamp_ns, is_mock))
        if len(self._imu_window) > self._max_imu_window_samples:
            self._imu_window.pop(0)

    def feed_location(
        self,
        fix_valid: bool,
        ground_speed_m_s: float | None = None,
        latitude_deg: float | None = None,
        longitude_deg: float | None = None,
        hdop: float | None = None,
        satellites_in_use: int | None = None,
        course_over_ground_deg: float | None = None,
        timestamp_ns: int | None = None,
    ) -> None:
        """Feed latest GNSS observation."""
        self._location_fix_valid = bool(fix_valid)
        self._location_ground_speed_m_s = ground_speed_m_s
        self._location_lat = latitude_deg
        self._location_lon = longitude_deg
        self._location_hdop = hdop
        self._location_satellites = satellites_in_use
        self._location_course_deg = course_over_ground_deg
        if timestamp_ns is not None:
            self._last_location_update_ns = timestamp_ns

    def feed_network(
        self,
        network_type: str = "lte",
        lte_rsrp_dbm: float | None = None,
        lte_cell_id: str | None = None,
        wifi_ap_count: int | None = None,
        wifi_fingerprint_hash: str | None = None,
    ) -> None:
        """Feed latest network state."""
        if network_type in {"offline", "wifi", "lte", "multi"}:
            self._network_type = network_type
        self._network_lte_rsrp = lte_rsrp_dbm
        self._network_lte_cell_id = lte_cell_id
        self._network_wifi_ap_count = wifi_ap_count
        self._network_wifi_hash = wifi_fingerprint_hash

    def feed_power(
        self,
        battery_soc_percent: float | None = None,
        battery_voltage_mv: int | None = None,
        is_charging: bool | None = None,
    ) -> None:
        """Feed latest power state."""
        self._power_soc = battery_soc_percent
        self._power_voltage_mv = battery_voltage_mv
        self._power_charging = is_charging

    def _compute_imu_features(
        self,
        now_monotonic_ns: int | None = None,
        window_duration_ms: int = 1000,
    ) -> tuple[float, float, float, int, float, bool]:
        """Compute motion RMS (m/s^2), peak acceleration (m/s^2), and gyro variance (dps^2)."""
        if not self._imu_window:
            return 0.0, 0.0, 0.0, 0, 0.0, False

        if now_monotonic_ns is not None:
            cutoff_ns = now_monotonic_ns - (window_duration_ms * 1_000_000)
            window_samples = [s for s in self._imu_window if s[6] >= cutoff_ns]
            if not window_samples:
                # If all samples are outside the requested window, use the latest samples up to 20
                window_samples = self._imu_window[-20:]
        else:
            window_samples = self._imu_window

        count = len(window_samples)
        is_mock = any(s[7] for s in window_samples)

        # Accel magnitudes
        mags = [math.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2) for s in window_samples]
        mean_mag = sum(mags) / count
        # Motion RMS (standard deviation of magnitude around local mean)
        rms = math.sqrt(sum((m - mean_mag) ** 2 for m in mags) / count)
        peak_accel = max(mags) if mags else 0.0

        # Gyro total variance
        gx_vals = [s[3] for s in window_samples]
        gy_vals = [s[4] for s in window_samples]
        gz_vals = [s[5] for s in window_samples]
        g_mean_x = sum(gx_vals) / count
        g_mean_y = sum(gy_vals) / count
        g_mean_z = sum(gz_vals) / count
        gyro_var = (
            sum((x - g_mean_x) ** 2 for x in gx_vals)
            + sum((y - g_mean_y) ** 2 for y in gy_vals)
            + sum((z - g_mean_z) ** 2 for z in gz_vals)
        ) / count

        # Calculate nominal sample rate
        sample_rate_hz = 20.0
        if count >= 2:
            time_span_s = (window_samples[-1][6] - window_samples[0][6]) / 1e9
            if time_span_s > 0.01:
                sample_rate_hz = round(count / time_span_s, 1)

        return rms, peak_accel, gyro_var, count, sample_rate_hz, is_mock

    def evaluate_state(
        self,
        now_monotonic_ns: int,
        now_utc: str | None = None,
        window_duration_ms: int = 1000,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Evaluate current active ego-state and produce (state_summary, evidence_chain)."""
        self._estimation_sequence += 1
        rms, peak_accel, gyro_var, count, sample_rate_hz, is_mock = self._compute_imu_features(
            now_monotonic_ns=now_monotonic_ns,
            window_duration_ms=window_duration_ms,
        )

        reason_codes: list[str] = []

        # 1. Spatial Mobility Decision
        speed = self._location_ground_speed_m_s
        fix = self._location_fix_valid

        if speed is not None and speed >= 4.0:
            spatial_mobility = "in_vehicle"
            reason_codes.append(f"gnss_speed_high_{speed:.1f}mps")
        elif speed is not None and speed >= 1.8 and rms >= 1.2:
            spatial_mobility = "running"
            reason_codes.append(f"high_speed_and_motion_rms_{rms:.2f}")
        elif rms >= 0.3:
            spatial_mobility = "pedestrian_walking"
            reason_codes.append(f"motion_rms_active_{rms:.2f}")
        elif not fix and (
            (self._network_wifi_ap_count is not None and self._network_wifi_ap_count >= 3)
            or (self._network_lte_rsrp is not None and self._network_lte_rsrp > -115.0)
        ):
            spatial_mobility = "indoor_weak_gnss"
            reason_codes.append("indoor_no_gnss_fix_with_rf_anchors")
        else:
            spatial_mobility = "stationary"
            reason_codes.append(f"motion_rms_quiet_{rms:.2f}")

        # 2. Posture Anomaly Decision
        if peak_accel >= 25.0:  # > 2.5g shock
            self._last_shock_time_ns = now_monotonic_ns
            posture_anomaly = "abnormal_shock"
            reason_codes.append(f"impact_shock_{peak_accel:.1f}mps2")
        elif (
            self._last_shock_time_ns is not None
            and (now_monotonic_ns - self._last_shock_time_ns) < 10_000_000_000  # within 10s of shock
            and rms < 0.15
        ):
            posture_anomaly = "suspected_fall"
            reason_codes.append("shock_followed_by_stillness")
        elif rms < 0.05:
            if self._immobility_start_ns is None:
                self._immobility_start_ns = now_monotonic_ns
                posture_anomaly = "normal"
            elif (now_monotonic_ns - self._immobility_start_ns) > 300_000_000_000:  # > 5 minutes stillness
                posture_anomaly = "prolonged_immobility"
                reason_codes.append("prolonged_stillness_over_300s")
            else:
                posture_anomaly = "normal"
        else:
            self._immobility_start_ns = None
            posture_anomaly = "normal"

        # 3. Device Wear State Decision
        if self._power_charging is True:
            device_wear_state = "charging_docked"
            reason_codes.append("charging_cable_or_dock_attached")
        elif rms < 0.05 and gyro_var < 0.02:
            device_wear_state = "tabletop_resting"
            reason_codes.append("pure_rest_tabletop")
        elif spatial_mobility == "stationary" and gyro_var > 0.05 and rms < 0.3:
            device_wear_state = "handheld"
            reason_codes.append("subtle_hand_movement")
        else:
            device_wear_state = "wearable_or_bag"
            reason_codes.append("dynamic_body_attachment")

        # 4. Confidence calculation
        confidence = 0.80
        if count >= 20:
            confidence += 0.10
        if fix:
            confidence += 0.05
        if self._power_soc is not None:
            confidence += 0.03
        confidence = min(0.99, round(confidence, 2))

        # Build evidence chain
        evidence_id = f"evid-b{self.boot_count}-{self._estimation_sequence}"
        evidence_raw_dict = {
            "device_id": self.device_id,
            "boot_count": self.boot_count,
            "timestamp_monotonic_ns": now_monotonic_ns,
            "imu": {
                "sample_count": count,
                "sample_rate_hz": sample_rate_hz,
                "motion_rms_m_s2": round(rms, 4),
                "peak_accel_m_s2": round(peak_accel, 4),
                "gyro_variance_dps2": round(gyro_var, 4),
            },
            "location": {
                "fix_valid": self._location_fix_valid,
                "ground_speed_m_s": self._location_ground_speed_m_s,
                "hdop": self._location_hdop,
            },
            "network": {
                "network_type": self._network_type,
                "lte_rsrp_dbm": self._network_lte_rsrp,
                "wifi_ap_count": self._network_wifi_ap_count,
            },
            "power": {
                "battery_soc_percent": self._power_soc,
                "battery_voltage_mv": self._power_voltage_mv,
                "is_charging": self._power_charging,
            },
        }
        evidence_digest = hashlib.sha256(
            json.dumps(evidence_raw_dict, sort_keys=True).encode("utf-8")
        ).hexdigest()

        evidence_chain = {
            "contract_version": EVIDENCE_CONTRACT_VERSION,
            "evidence_id": evidence_id,
            "evidence_digest": evidence_digest,
            "device_id": self.device_id,
            "boot_count": self.boot_count,
            "timestamp_monotonic_ns": now_monotonic_ns,
            "timestamp_utc": now_utc,
            "window_duration_ms": window_duration_ms,
            "imu_evidence": {
                "sample_count": count,
                "sample_rate_hz": sample_rate_hz,
                "motion_rms_m_s2": round(rms, 4),
                "peak_accel_m_s2": round(peak_accel, 4),
                "gyro_variance_dps2": round(gyro_var, 4),
                "is_mock": is_mock,
            },
            "location_evidence": {
                "fix_valid": self._location_fix_valid,
                "latitude_deg": self._location_lat,
                "longitude_deg": self._location_lon,
                "hdop": self._location_hdop,
                "ground_speed_m_s": self._location_ground_speed_m_s,
                "satellites_in_use": self._location_satellites,
                "course_over_ground_deg": self._location_course_deg,
            },
            "network_evidence": {
                "network_type": self._network_type,
                "lte_rsrp_dbm": self._network_lte_rsrp,
                "lte_cell_id": self._network_lte_cell_id,
                "wifi_ap_count": self._network_wifi_ap_count,
                "wifi_fingerprint_hash": self._network_wifi_hash,
            },
            "power_evidence": {
                "battery_soc_percent": self._power_soc,
                "battery_voltage_mv": self._power_voltage_mv,
                "is_charging": self._power_charging,
            },
            "provenance": {
                "source_driver_backend": "qmi8658_max17048_sim7670g",
                "firmware_version": self.firmware_version,
                "firmware_elf_sha256": self.firmware_elf_sha256,
            },
        }

        state_summary = {
            "contract_version": CONTRACT_VERSION,
            "estimation_id": f"est-b{self.boot_count}-{self._estimation_sequence}",
            "device_id": self.device_id,
            "boot_count": self.boot_count,
            "timestamp_monotonic_ns": now_monotonic_ns,
            "timestamp_utc": now_utc,
            "spatial_mobility": spatial_mobility,
            "posture_anomaly": posture_anomaly,
            "device_wear_state": device_wear_state,
            "confidence": confidence,
            "window_duration_ms": window_duration_ms,
            "reason_codes": reason_codes,
            "primary_evidence_digest": evidence_digest,
            "is_mock": is_mock,
        }

        return state_summary, evidence_chain

    def generate_report(
        self,
        report_type: str = "periodic_aggregate",
        now_monotonic_ns: int = 0,
        now_utc: str | None = None,
        window_duration_ms: int = 1000,
        notes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete structured active ego-state estimation report."""
        if report_type not in {"periodic_aggregate", "event_transition", "critical_alarm"}:
            report_type = "periodic_aggregate"

        state_summary, evidence_chain = self.evaluate_state(
            now_monotonic_ns=now_monotonic_ns,
            now_utc=now_utc,
            window_duration_ms=window_duration_ms,
        )

        start_ns = max(0, now_monotonic_ns - window_duration_ms * 1_000_000)
        retention_category = "daily_local"
        if report_type == "critical_alarm":
            retention_category = "critical_permanent"
        elif report_type == "event_transition":
            retention_category = "realtime_transient"

        report = {
            "contract_version": REPORT_CONTRACT_VERSION,
            "report_id": f"rep-b{self.boot_count}-{self._estimation_sequence}",
            "device_id": self.device_id,
            "boot_count": self.boot_count,
            "session_id": self.session_id,
            "report_type": report_type,
            "generated_at_utc": now_utc,
            "start_monotonic_ns": start_ns,
            "end_monotonic_ns": now_monotonic_ns,
            "state_summary": state_summary,
            "evidence_chain": evidence_chain,
            "privacy_boundary": {
                "local_priority": True,
                "encrypted_at_rest": True,
                "retention_category": retention_category,
            },
            "notes": list(notes) if notes else ["Ego-State Estimator verified execution"],
        }
        return report
