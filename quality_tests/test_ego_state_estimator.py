from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pc_simulator.ego_state_estimator import (
    CONTRACT_VERSION,
    EVIDENCE_CONTRACT_VERSION,
    REPORT_CONTRACT_VERSION,
    EgoStateEstimator,
)


class TestEgoStateEstimator(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.contracts_dir = self.repo_root / "shared" / "contracts"

        self.estimation_schema = json.loads(
            (self.contracts_dir / "ego_state_estimation_v0.schema.json").read_text(encoding="utf-8")
        )
        self.evidence_schema = json.loads(
            (self.contracts_dir / "ego_state_evidence_chain_v0.schema.json").read_text(encoding="utf-8")
        )
        self.report_schema = json.loads(
            (self.contracts_dir / "ego_state_report_v0.schema.json").read_text(encoding="utf-8")
        )

        reg = Registry().with_resources(
            [
                ("ego_state_estimation_v0.schema.json", Resource.from_contents(self.estimation_schema)),
                ("ego_state_evidence_chain_v0.schema.json", Resource.from_contents(self.evidence_schema)),
                (
                    "https://ego.local/contracts/ego_state_estimation_v0.schema.json",
                    Resource.from_contents(self.estimation_schema),
                ),
                (
                    "https://ego.local/contracts/ego_state_evidence_chain_v0.schema.json",
                    Resource.from_contents(self.evidence_schema),
                ),
            ]
        )

        self.estimation_validator = Draft202012Validator(self.estimation_schema)
        self.evidence_validator = Draft202012Validator(self.evidence_schema)
        self.report_validator = Draft202012Validator(self.report_schema, registry=reg)

    def test_stationary_bench_state_and_schema_validation(self) -> None:
        estimator = EgoStateEstimator(boot_count=171, session_id="test-session-171")

        # Simulate 20 samples of bench resting (approx 1g Z, very low noise)
        base_time = 1_000_000_000
        for i in range(20):
            estimator.feed_imu_sample(
                ax_mg=5.0,
                ay_mg=-3.0,
                az_mg=1002.0,
                gx_mdps=10.0,
                gy_mdps=-15.0,
                gz_mdps=5.0,
                timestamp_ns=base_time + i * 50_000_000,
                is_mock=False,
            )

        estimator.feed_location(
            fix_valid=True,
            ground_speed_m_s=0.0,
            latitude_deg=22.5431,
            longitude_deg=114.0579,
            hdop=1.1,
            satellites_in_use=16,
            course_over_ground_deg=0.0,
        )
        estimator.feed_power(battery_soc_percent=99.0, battery_voltage_mv=4250, is_charging=False)
        estimator.feed_network(network_type="lte", lte_rsrp_dbm=-85.0, lte_cell_id="460-00-1111")

        report = estimator.generate_report(
            report_type="periodic_aggregate",
            now_monotonic_ns=base_time + 20 * 50_000_000,
            now_utc="2026-09-19T03:45:00.000Z",
        )

        state = report["state_summary"]
        evidence = report["evidence_chain"]

        self.assertEqual(state["spatial_mobility"], "stationary")
        self.assertEqual(state["posture_anomaly"], "normal")
        self.assertEqual(state["device_wear_state"], "tabletop_resting")
        self.assertGreaterEqual(state["confidence"], 0.90)

        # Validate schemas
        self.estimation_validator.validate(state)
        self.evidence_validator.validate(evidence)
        self.report_validator.validate(report)

        # Digest verification
        self.assertEqual(state["primary_evidence_digest"], evidence["evidence_digest"])

    def test_pedestrian_walking_inference(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)

        # Walking pattern: periodic accel variations with rms > 0.3 m/s^2
        base_time = 2_000_000_000
        for i in range(30):
            # Alternating steps with footstrike and swing phase
            step_az = 1400.0 if (i % 4 < 2) else 650.0
            estimator.feed_imu_sample(
                ax_mg=200.0,
                ay_mg=50.0,
                az_mg=step_az,
                gx_mdps=200.0,
                gy_mdps=-150.0,
                gz_mdps=100.0,
                timestamp_ns=base_time + i * 50_000_000,
            )

        estimator.feed_location(
            fix_valid=True,
            ground_speed_m_s=1.2,
            latitude_deg=22.5432,
            longitude_deg=114.0580,
            hdop=1.4,
        )

        state, evidence = estimator.evaluate_state(now_monotonic_ns=base_time + 30 * 50_000_000)
        self.assertEqual(state["spatial_mobility"], "pedestrian_walking")
        self.assertEqual(state["device_wear_state"], "wearable_or_bag")
        self.estimation_validator.validate(state)
        self.evidence_validator.validate(evidence)

    def test_running_and_vehicle_inference(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)

        # Running: speed >= 1.8 and rms >= 1.2
        base_time = 3_000_000_000
        for i in range(25):
            high_accel = 1500.0 if (i % 2 == 0) else -800.0
            estimator.feed_imu_sample(
                ax_mg=high_accel,
                ay_mg=300.0,
                az_mg=1200.0,
                gx_mdps=500.0,
                gy_mdps=-400.0,
                gz_mdps=300.0,
                timestamp_ns=base_time + i * 50_000_000,
            )

        estimator.feed_location(fix_valid=True, ground_speed_m_s=2.8)
        state, _ = estimator.evaluate_state(now_monotonic_ns=base_time + 25 * 50_000_000)
        self.assertEqual(state["spatial_mobility"], "running")

        # In vehicle: speed >= 4.0 m/s
        estimator.feed_location(fix_valid=True, ground_speed_m_s=12.5)
        state_veh, _ = estimator.evaluate_state(now_monotonic_ns=base_time + 26 * 50_000_000)
        self.assertEqual(state_veh["spatial_mobility"], "in_vehicle")

    def test_shock_and_suspected_fall_detection(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)

        t0 = 5_000_000_000
        # Normal motion
        estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=t0)

        # Severe impact shock: > 25 m/s^2 (approx 2600 mg = 25.5 m/s^2)
        estimator.feed_imu_sample(2600, 500, 1200, 3000, 2000, 1000, timestamp_ns=t0 + 50_000_000)

        state_shock, _ = estimator.evaluate_state(now_monotonic_ns=t0 + 50_000_000)
        self.assertEqual(state_shock["posture_anomaly"], "abnormal_shock")

        # After shock, rapid stillness ensues (simulating fall & unconsciousness / immobility)
        t_after = t0 + 2_000_000_000  # 2 seconds after shock
        # Clear rolling window by feeding resting samples
        for i in range(25):
            estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=t_after + i * 50_000_000)

        report_fall = estimator.generate_report(
            report_type="critical_alarm",
            now_monotonic_ns=t_after + 25 * 50_000_000,
            now_utc="2026-09-19T03:50:00.000Z",
            notes=["Critical fall alarm triggered"],
        )

        self.assertEqual(report_fall["report_type"], "critical_alarm")
        self.assertEqual(report_fall["privacy_boundary"]["retention_category"], "critical_permanent")
        self.assertEqual(report_fall["state_summary"]["posture_anomaly"], "suspected_fall")
        self.report_validator.validate(report_fall)

    def test_charging_docked_state(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)
        estimator.feed_power(battery_soc_percent=80.0, battery_voltage_mv=4100, is_charging=True)
        estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=1000)

        state, _ = estimator.evaluate_state(now_monotonic_ns=2000)
        self.assertEqual(state["device_wear_state"], "charging_docked")

    def test_handheld_state(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)
        # Stationary linear accel (rms < 0.3) but subtle hand tremor / rotational movement (gyro_var > 0.05)
        for i in range(20):
            estimator.feed_imu_sample(
                ax_mg=10.0,
                ay_mg=-5.0,
                az_mg=1000.0,
                gx_mdps=300.0 if i % 2 == 0 else -250.0,
                gy_mdps=200.0 if i % 2 == 0 else -180.0,
                gz_mdps=150.0 if i % 2 == 0 else -120.0,
                timestamp_ns=i * 50_000_000,
            )

        state, _ = estimator.evaluate_state(now_monotonic_ns=20 * 50_000_000)
        self.assertEqual(state["spatial_mobility"], "stationary")
        self.assertEqual(state["device_wear_state"], "handheld")

    def test_indoor_weak_gnss_state(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)
        for i in range(20):
            estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=i * 50_000_000)

        estimator.feed_location(fix_valid=False)
        estimator.feed_network(network_type="wifi", wifi_ap_count=5)

        state, _ = estimator.evaluate_state(now_monotonic_ns=20 * 50_000_000)
        self.assertEqual(state["spatial_mobility"], "indoor_weak_gnss")

    def test_prolonged_immobility_state(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)
        for i in range(20):
            estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=i * 50_000_000)

        # First evaluation starts immobility timer
        t1 = 1_000_000_000
        state1, _ = estimator.evaluate_state(now_monotonic_ns=t1)
        self.assertEqual(state1["posture_anomaly"], "normal")

        # 301 seconds later of continuous stillness
        t2 = t1 + 301_000_000_000
        for i in range(20):
            estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=t2 - (20 - i) * 50_000_000)
        state2, _ = estimator.evaluate_state(now_monotonic_ns=t2)
        self.assertEqual(state2["posture_anomaly"], "prolonged_immobility")

    def test_tamper_evidence_digest_detection(self) -> None:
        estimator = EgoStateEstimator(boot_count=171)
        for i in range(20):
            estimator.feed_imu_sample(0, 0, 1000, 0, 0, 0, timestamp_ns=i * 50_000_000)

        report = estimator.generate_report(now_monotonic_ns=1_000_000_000)
        # Tamper with the evidence chain IMU data
        report["evidence_chain"]["imu_evidence"]["peak_accel_m_s2"] = 99.99

        # Recomputing digest should mismatch the recorded evidence_digest
        tampered_evidence_raw = {
            "device_id": report["evidence_chain"]["device_id"],
            "boot_count": report["evidence_chain"]["boot_count"],
            "timestamp_monotonic_ns": report["evidence_chain"]["timestamp_monotonic_ns"],
            "imu": {
                "sample_count": report["evidence_chain"]["imu_evidence"]["sample_count"],
                "sample_rate_hz": report["evidence_chain"]["imu_evidence"]["sample_rate_hz"],
                "motion_rms_m_s2": report["evidence_chain"]["imu_evidence"]["motion_rms_m_s2"],
                "peak_accel_m_s2": report["evidence_chain"]["imu_evidence"]["peak_accel_m_s2"],
                "gyro_variance_dps2": report["evidence_chain"]["imu_evidence"]["gyro_variance_dps2"],
            },
            "location": {
                "fix_valid": report["evidence_chain"]["location_evidence"]["fix_valid"],
                "ground_speed_m_s": report["evidence_chain"]["location_evidence"]["ground_speed_m_s"],
                "hdop": report["evidence_chain"]["location_evidence"]["hdop"],
            },
            "network": {
                "network_type": report["evidence_chain"]["network_evidence"]["network_type"],
                "lte_rsrp_dbm": report["evidence_chain"]["network_evidence"]["lte_rsrp_dbm"],
                "wifi_ap_count": report["evidence_chain"]["network_evidence"]["wifi_ap_count"],
            },
            "power": {
                "battery_soc_percent": report["evidence_chain"]["power_evidence"]["battery_soc_percent"],
                "battery_voltage_mv": report["evidence_chain"]["power_evidence"]["battery_voltage_mv"],
                "is_charging": report["evidence_chain"]["power_evidence"]["is_charging"],
            },
        }
        recomputed_hash = hashlib.sha256(
            json.dumps(tampered_evidence_raw, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(recomputed_hash, report["evidence_chain"]["evidence_digest"])


if __name__ == "__main__":
    unittest.main()
