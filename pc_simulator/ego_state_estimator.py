"""Deterministic Active Ego-State Estimator and Evidence Chain Generator.

Uses bounded local sensor windows (IMU, GNSS, network and battery) to produce
engineering rule estimates. Report metadata does not implement storage,
encryption or retention enforcement.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Sequence


CONTRACT_VERSION = "egolink.ego_state_estimation.v0.1"
EVIDENCE_CONTRACT_VERSION = "egolink.ego_state_evidence_chain.v0.1"
REPORT_CONTRACT_VERSION = "egolink.ego_state_report.v0.1"

# Engineering freshness bounds, not product accuracy or detection guarantees.
IMU_MAX_AGE_NS = 1_000_000_000
SOURCE_MAX_AGE_NS = 30_000_000_000
MAX_WINDOW_MS = 10_000


def _number(value: Any, low: float, high: float, *, optional: bool = False) -> bool:
    return (optional and value is None) or (
        isinstance(value, (float, int)) and not isinstance(value, bool)
        # Bound integers before math.isfinite converts them to float: an
        # untrusted arbitrary-size JSON integer must be rejected, not overflow.
        and low <= value <= high and math.isfinite(value)
    )


def _timestamp(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1

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
        self._last_imu_input_ns = -1
        self._last_evaluation_ns = -1
        self._imu_invalid = False
        self._imu_invalid_is_mock = False
        self._imu_future_rejected = False
        self._last_imu_is_mock = False
        self._sources = {name: {"timestamp": -1, "valid": False, "is_mock": False, "future_rejected": False}
                         for name in ("gnss", "network", "power")}

    def _admit(self, source: str, timestamp_ns: int | None, valid: bool, is_mock: bool) -> bool:
        # Missing timing is not silently replaced by ingest/evaluation time.
        if timestamp_ns is None:
            self._sources[source] = {"timestamp": -1, "valid": False, "is_mock": bool(is_mock), "future_rejected": False}
            return False
        if not self._accepts_source_time(timestamp_ns, self._sources[source]["timestamp"], self._sources[source]["future_rejected"]):
            return False
        self._sources[source] = {"timestamp": timestamp_ns, "valid": valid, "is_mock": bool(is_mock), "future_rejected": False}
        return valid

    def _accepts_source_time(self, incoming: Any, previous: int, future_rejected: bool) -> bool:
        return _timestamp(incoming) and (incoming > previous or (
            future_rejected and self._last_evaluation_ns >= 0 and previous > self._last_evaluation_ns
            and incoming >= self._last_evaluation_ns))

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
    ) -> bool:
        """Feed a single 6-axis IMU measurement (accel in mg, gyro in mdps)."""
        if not self._accepts_source_time(timestamp_ns, self._last_imu_input_ns, self._imu_future_rejected):
            return False
        if timestamp_ns <= self._last_imu_input_ns:
            self._imu_window.clear()
            self._last_shock_time_ns = None
            self._immobility_start_ns = None
        if self._last_imu_input_ns >= 0 and timestamp_ns - self._last_imu_input_ns > IMU_MAX_AGE_NS:
            self._immobility_start_ns = None
        self._last_imu_input_ns = timestamp_ns
        self._last_imu_is_mock = bool(is_mock)
        self._imu_future_rejected = False
        valid = all(_number(v, -16000, 16000) for v in (ax_mg, ay_mg, az_mg)) and all(
            _number(v, -4000000, 4000000) for v in (gx_mdps, gy_mdps, gz_mdps))
        if not valid:
            self._imu_window.clear()
            self._imu_invalid = True
            self._imu_invalid_is_mock = bool(is_mock)
            self._immobility_start_ns = None
            self._last_shock_time_ns = None
            return False
        self._imu_invalid = False
        self._imu_invalid_is_mock = False
        if is_mock:
            self._immobility_start_ns = None
            self._last_shock_time_ns = None
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
        return True

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
        is_mock: bool = False,
    ) -> bool:
        """Feed latest GNSS observation."""
        valid = isinstance(fix_valid, bool) and all((
            _number(ground_speed_m_s, 0, 200, optional=not fix_valid),
            _number(latitude_deg, -90, 90, optional=True),
            _number(longitude_deg, -180, 180, optional=True),
            _number(hdop, 0, 1000, optional=True),
            _number(course_over_ground_deg, 0, 360, optional=True),
            satellites_in_use is None or (isinstance(satellites_in_use, int) and not isinstance(satellites_in_use, bool) and 0 <= satellites_in_use <= 65535),
        ))
        if not self._admit("gnss", timestamp_ns, valid, is_mock):
            return False
        self._location_fix_valid = bool(fix_valid)
        self._location_ground_speed_m_s = ground_speed_m_s
        self._location_lat = latitude_deg
        self._location_lon = longitude_deg
        self._location_hdop = hdop
        self._location_satellites = satellites_in_use
        self._location_course_deg = course_over_ground_deg
        if timestamp_ns is not None:
            self._last_location_update_ns = timestamp_ns
        return True

    def feed_network(
        self,
        network_type: str = "lte",
        lte_rsrp_dbm: float | None = None,
        lte_cell_id: str | None = None,
        wifi_ap_count: int | None = None,
        wifi_fingerprint_hash: str | None = None,
        timestamp_ns: int | None = None,
        is_mock: bool = False,
    ) -> bool:
        """Feed latest network state."""
        valid = (isinstance(network_type, str) and network_type in {"offline", "wifi", "lte", "multi"}
                 and _number(lte_rsrp_dbm, -160, 0, optional=network_type not in {"lte", "multi"})
                 and (lte_rsrp_dbm is None or lte_rsrp_dbm < 0)
                 and (wifi_ap_count is None or (isinstance(wifi_ap_count, int) and not isinstance(wifi_ap_count, bool) and 0 <= wifi_ap_count <= 65535))
                 and (wifi_fingerprint_hash is None or (isinstance(wifi_fingerprint_hash, str) and len(wifi_fingerprint_hash) == 64 and all(c in "0123456789abcdef" for c in wifi_fingerprint_hash))))
        if not self._admit("network", timestamp_ns, valid, is_mock):
            return False
        if network_type in {"offline", "wifi", "lte", "multi"}:
            self._network_type = network_type
        self._network_lte_rsrp = lte_rsrp_dbm
        self._network_lte_cell_id = lte_cell_id
        self._network_wifi_ap_count = wifi_ap_count
        self._network_wifi_hash = wifi_fingerprint_hash
        return True

    def feed_power(
        self,
        battery_soc_percent: float | None = None,
        battery_voltage_mv: int | None = None,
        is_charging: bool | None = None,
        timestamp_ns: int | None = None,
        is_mock: bool = False,
    ) -> bool:
        """Feed latest power state."""
        valid = (_number(battery_soc_percent, 0, 100)
                 and isinstance(battery_voltage_mv, int) and not isinstance(battery_voltage_mv, bool)
                 and 0 <= battery_voltage_mv <= 6000
                 and (is_charging is None or isinstance(is_charging, bool)))
        if not self._admit("power", timestamp_ns, valid, is_mock):
            return False
        self._power_soc = battery_soc_percent
        self._power_voltage_mv = battery_voltage_mv
        self._power_charging = is_charging
        return True

    def _compute_imu_features(
        self,
        now_monotonic_ns: int | None = None,
        window_duration_ms: int = 1000,
    ) -> tuple[float, float, float, int, float, bool, int, int]:
        """Compute motion RMS (m/s^2), peak acceleration (m/s^2), and gyro variance (dps^2)."""
        if not self._imu_window:
            return 0.0, 0.0, 0.0, 0, 0.0, False, -1, -1

        if now_monotonic_ns is not None:
            cutoff_ns = now_monotonic_ns - (window_duration_ms * 1_000_000)
            window_samples = [s for s in self._imu_window if cutoff_ns <= s[6] <= now_monotonic_ns]
        else:
            window_samples = self._imu_window

        count = len(window_samples)
        if count == 0:
            return 0.0, 0.0, 0.0, 0, 0.0, False, -1, -1
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
        sample_rate_hz = 0.0
        if count >= 2:
            time_span_s = (window_samples[-1][6] - window_samples[0][6]) / 1e9
            if time_span_s > 0:
                sample_rate_hz = round((count - 1) / time_span_s, 1)

        shock_ns = max((s[6] for s, mag in zip(window_samples, mags) if mag >= 25.0), default=-1)
        return rms, peak_accel, gyro_var, count, sample_rate_hz, is_mock, window_samples[-1][6], shock_ns

    def evaluate_state(
        self,
        now_monotonic_ns: int,
        now_utc: str | None = None,
        window_duration_ms: int = 1000,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Evaluate current active ego-state and produce (state_summary, evidence_chain)."""
        if (not _timestamp(now_monotonic_ns) or now_monotonic_ns < self._last_evaluation_ns
                or not isinstance(window_duration_ms, int) or isinstance(window_duration_ms, bool)
                or not 100 <= window_duration_ms <= MAX_WINDOW_MS):
            raise ValueError("invalid or regressed evaluation time/window")
        self._last_evaluation_ns = now_monotonic_ns
        self._imu_future_rejected = self._last_imu_input_ns > now_monotonic_ns
        for source in self._sources.values():
            source["future_rejected"] = source["timestamp"] > now_monotonic_ns
        self._estimation_sequence += 1
        rms, peak_accel, gyro_var, count, sample_rate_hz, imu_mock, latest_ns, shock_ns = self._compute_imu_features(
            now_monotonic_ns=now_monotonic_ns,
            window_duration_ms=window_duration_ms,
        )

        reason_codes: list[str] = []
        imu_problem = None
        if self._imu_invalid:
            imu_problem = "imu_invalid"
        elif self._last_imu_input_ns > now_monotonic_ns:
            imu_problem = "imu_future"
        elif self._last_imu_input_ns < 0:
            imu_problem = "imu_missing"
        elif count == 0 or now_monotonic_ns - latest_ns > IMU_MAX_AGE_NS:
            imu_problem = "imu_stale"
        elif imu_mock:
            imu_problem = "imu_mock"
        elif count < 2:
            imu_problem = "imu_insufficient_samples"
        imu_ok = imu_problem is None
        if not imu_ok:
            reason_codes.append(imu_problem)
            self._immobility_start_ns = None
            self._last_shock_time_ns = None

        def usable(name: str) -> bool:
            source = self._sources[name]
            ts = source["timestamp"]
            problem = ("missing" if ts < 0 else "invalid" if not source["valid"] else
                       "future" if ts > now_monotonic_ns else
                       "stale" if now_monotonic_ns - ts > SOURCE_MAX_AGE_NS else
                       "mock" if source["is_mock"] else None)
            if problem:
                reason_codes.append(f"{name}_{problem}")
            return problem is None

        location_ok, network_ok, power_ok = (usable(name) for name in ("gnss", "network", "power"))
        if power_ok and self._power_charging is None:
            reason_codes.append("power_charging_unknown")
        is_mock = (imu_mock or self._imu_invalid_is_mock
                   or (self._imu_future_rejected and self._last_imu_is_mock)
                   or any(s["is_mock"] for s in self._sources.values()))

        # 1. Spatial Mobility Decision
        speed = self._location_ground_speed_m_s
        fix = location_ok and self._location_fix_valid
        spatial_mobility = "unknown"

        if fix and speed is not None and speed >= 4.0:
            spatial_mobility = "in_vehicle"
            reason_codes.append(f"gnss_speed_high_{speed:.1f}mps")
        elif fix and imu_ok and speed is not None and speed >= 1.8 and rms >= 1.2:
            spatial_mobility = "running"
            reason_codes.append(f"high_speed_and_motion_rms_{rms:.2f}")
        elif imu_ok and rms >= 0.3:
            spatial_mobility = "pedestrian_walking"
            reason_codes.append(f"motion_rms_active_{rms:.2f}")
        elif imu_ok and location_ok and not fix and network_ok and (
            (self._network_wifi_ap_count is not None and self._network_wifi_ap_count >= 3)
            or (self._network_type in {"lte", "multi"} and self._network_lte_rsrp is not None
                and self._network_lte_rsrp != 0 and self._network_lte_rsrp > -115.0)
        ):
            spatial_mobility = "indoor_weak_gnss"
            reason_codes.append("rf_no_fix_indoor_candidate")
        elif imu_ok:
            spatial_mobility = "stationary"
            reason_codes.append(f"motion_rms_quiet_{rms:.2f}")

        # 2. Posture Anomaly Decision
        if not imu_ok:
            posture_anomaly = "unknown"
        elif peak_accel >= 25.0:  # > 2.5g shock
            self._immobility_start_ns = None
            # Re-evaluation of a window never gives an old impact a new event time.
            self._last_shock_time_ns = max(self._last_shock_time_ns or -1, shock_ns)
            posture_anomaly = "abnormal_shock"
            reason_codes.append(f"impact_shock_{peak_accel:.1f}mps2")
        elif (
            self._last_shock_time_ns is not None
            and (now_monotonic_ns - self._last_shock_time_ns) < 10_000_000_000  # within 10s of shock
            and latest_ns > self._last_shock_time_ns
            and rms < 0.15
        ):
            self._immobility_start_ns = None
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
        device_wear_state = "unknown"
        if power_ok and self._power_charging is True:
            device_wear_state = "charging_docked"
            reason_codes.append("charging_cable_or_dock_attached")
        elif imu_ok and rms < 0.05 and gyro_var < 0.02:
            device_wear_state = "tabletop_resting"
            reason_codes.append("pure_rest_tabletop")
        elif imu_ok and spatial_mobility == "stationary" and gyro_var > 0.05 and rms < 0.3:
            device_wear_state = "handheld"
            reason_codes.append("subtle_hand_movement")
        elif imu_ok:
            device_wear_state = "wearable_or_bag"
            reason_codes.append("dynamic_body_attachment")

        # 4. Confidence calculation
        # Heuristic completeness score, not a calibrated probability.
        complete = imu_ok and fix and network_ok and power_ok and self._power_charging is not None
        if complete:
            confidence = 0.98 if count >= 20 else 0.88
        else:
            confidence = 0.5 if any(s != "unknown" for s in (spatial_mobility, posture_anomaly, device_wear_state)) else 0.0
            reason_codes.append("partial_evidence_low_confidence")

        # Unusable observations must not leak old/non-finite values as current evidence.
        location = {"fix_valid": fix, "latitude_deg": self._location_lat if location_ok else None,
                    "longitude_deg": self._location_lon if location_ok else None,
                    "hdop": self._location_hdop if location_ok else None,
                    "ground_speed_m_s": speed if location_ok else None,
                    "satellites_in_use": self._location_satellites if location_ok else None,
                    "course_over_ground_deg": self._location_course_deg if location_ok else None}
        network = {"network_type": self._network_type if network_ok else "offline",
                   "lte_rsrp_dbm": self._network_lte_rsrp if network_ok else None,
                   "lte_cell_id": self._network_lte_cell_id if network_ok else None,
                   "wifi_ap_count": self._network_wifi_ap_count if network_ok else None,
                   "wifi_fingerprint_hash": self._network_wifi_hash if network_ok else None}
        power = {"battery_soc_percent": self._power_soc if power_ok else None,
                 "battery_voltage_mv": self._power_voltage_mv if power_ok else None,
                 "is_charging": self._power_charging if power_ok else None}

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
                "fix_valid": fix,
                "ground_speed_m_s": location["ground_speed_m_s"],
                "hdop": location["hdop"],
            },
            "network": {
                "network_type": network["network_type"],
                "lte_rsrp_dbm": network["lte_rsrp_dbm"],
                "wifi_ap_count": network["wifi_ap_count"],
            },
            "power": {
                **power,
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
                "is_mock": imu_mock,
            },
            "location_evidence": location,
            "network_evidence": network,
            "power_evidence": power,
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
                "encrypted_at_rest": False,
                "retention_category": retention_category,
            },
            "notes": list(notes or []) + [
                "Engineering rule estimate; not a validated safety or accuracy claim.",
                "In-memory report only; persistence, encryption and retention enforcement are not implemented here.",
                "The producer-generated feature-summary digest is not a signature or verification of the complete raw evidence chain; C/Python canonical digest interoperability has not been established.",
            ],
        }
        return report
