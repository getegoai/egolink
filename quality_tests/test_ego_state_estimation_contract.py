from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import jsonschema
from jsonschema import Draft202012Validator


class TestEgoStateEstimationContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.contracts_dir = self.repo_root / "shared" / "contracts"

        self.estimation_schema_path = self.contracts_dir / "ego_state_estimation_v0.schema.json"
        self.evidence_schema_path = self.contracts_dir / "ego_state_evidence_chain_v0.schema.json"
        self.report_schema_path = self.contracts_dir / "ego_state_report_v0.schema.json"

        self.assertTrue(self.estimation_schema_path.is_file(), f"Missing {self.estimation_schema_path}")
        self.assertTrue(self.evidence_schema_path.is_file(), f"Missing {self.evidence_schema_path}")
        self.assertTrue(self.report_schema_path.is_file(), f"Missing {self.report_schema_path}")

        self.estimation_schema = json.loads(self.estimation_schema_path.read_text(encoding="utf-8"))
        self.evidence_schema = json.loads(self.evidence_schema_path.read_text(encoding="utf-8"))
        self.report_schema = json.loads(self.report_schema_path.read_text(encoding="utf-8"))

    def test_schemas_are_valid_draft202012(self) -> None:
        Draft202012Validator.check_schema(self.estimation_schema)
        Draft202012Validator.check_schema(self.evidence_schema)
        Draft202012Validator.check_schema(self.report_schema)

    def test_estimation_schema_valid_instance(self) -> None:
        validator = Draft202012Validator(self.estimation_schema)
        sample = {
            "contract_version": "egolink.ego_state_estimation.v0.1",
            "estimation_id": "est-001",
            "device_id": "ego-link-001",
            "boot_count": 171,
            "timestamp_monotonic_ns": 123456789000,
            "timestamp_utc": "2026-09-19T03:37:00.000Z",
            "spatial_mobility": "stationary",
            "posture_anomaly": "normal",
            "device_wear_state": "tabletop_resting",
            "confidence": 0.98,
            "window_duration_ms": 2000,
            "reason_codes": ["motion_rms_below_stationary_threshold", "gnss_speed_zero"],
            "primary_evidence_digest": hashlib.sha256(b"sample_evidence").hexdigest(),
            "is_mock": False,
        }
        validator.validate(sample)

    def test_estimation_schema_rejects_invalid_values(self) -> None:
        validator = Draft202012Validator(self.estimation_schema)
        base = {
            "contract_version": "egolink.ego_state_estimation.v0.1",
            "estimation_id": "est-001",
            "device_id": "ego-link-001",
            "boot_count": 171,
            "timestamp_monotonic_ns": 123456789000,
            "timestamp_utc": "2026-09-19T03:37:00.000Z",
            "spatial_mobility": "stationary",
            "posture_anomaly": "normal",
            "device_wear_state": "tabletop_resting",
            "confidence": 0.98,
            "window_duration_ms": 2000,
            "reason_codes": ["ok"],
            "primary_evidence_digest": hashlib.sha256(b"sample").hexdigest(),
            "is_mock": False,
        }

        # Invalid spatial_mobility enum
        bad_mob = dict(base, spatial_mobility="flying")
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad_mob)

        # Invalid confidence > 1.0
        bad_conf = dict(base, confidence=1.5)
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad_conf)

        # Invalid primary_evidence_digest (not 64 hex characters)
        bad_hash = dict(base, primary_evidence_digest="not-a-hash")
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad_hash)

    def test_evidence_chain_schema_valid_instance(self) -> None:
        validator = Draft202012Validator(self.evidence_schema)
        sample = {
            "contract_version": "egolink.ego_state_evidence_chain.v0.1",
            "evidence_id": "evid-171-001",
            "evidence_digest": hashlib.sha256(b"multi_sensor_evidence").hexdigest(),
            "device_id": "ego-link-001",
            "boot_count": 171,
            "timestamp_monotonic_ns": 123456789000,
            "timestamp_utc": "2026-09-19T03:37:00.000Z",
            "window_duration_ms": 1000,
            "imu_evidence": {
                "sample_count": 20,
                "sample_rate_hz": 20.0,
                "motion_rms_m_s2": 0.157,
                "peak_accel_m_s2": 0.312,
                "gyro_variance_dps2": 0.05,
                "is_mock": False,
            },
            "location_evidence": {
                "fix_valid": True,
                "latitude_deg": 22.5431,
                "longitude_deg": 114.0579,
                "hdop": 1.2,
                "ground_speed_m_s": 0.0,
                "satellites_in_use": 14,
                "course_over_ground_deg": 0.0,
            },
            "network_evidence": {
                "network_type": "lte",
                "lte_rsrp_dbm": -88.0,
                "lte_cell_id": "460-00-12345-67",
                "wifi_ap_count": 4,
                "wifi_fingerprint_hash": hashlib.sha256(b"wifi_aps").hexdigest(),
            },
            "power_evidence": {
                "battery_soc_percent": 98.5,
                "battery_voltage_mv": 4210,
                "is_charging": False,
            },
            "provenance": {
                "source_driver_backend": "qmi8658_max17048_sim7670g",
                "firmware_version": "0.1.0-sensor-policy-continuous-021",
                "firmware_elf_sha256": "2411325042246be77f9e696f9d1cc7c89840f97e46fc4a7b5c928bc7c1d39e87",
            },
        }
        validator.validate(sample)

    def test_report_schema_resolves_and_validates(self) -> None:
        # Build registry or store for cross-schema references
        schema_store = {
            self.estimation_schema["$id"]: self.estimation_schema,
            "ego_state_estimation_v0.schema.json": self.estimation_schema,
            self.evidence_schema["$id"]: self.evidence_schema,
            "ego_state_evidence_chain_v0.schema.json": self.evidence_schema,
            self.report_schema["$id"]: self.report_schema,
        }
        from referencing import Registry, Resource

        reg = Registry().with_resources(
            [
                (
                    "ego_state_estimation_v0.schema.json",
                    Resource.from_contents(self.estimation_schema),
                ),
                (
                    "ego_state_evidence_chain_v0.schema.json",
                    Resource.from_contents(self.evidence_schema),
                ),
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

        validator = Draft202012Validator(self.report_schema, registry=reg)

        evidence = {
            "contract_version": "egolink.ego_state_evidence_chain.v0.1",
            "evidence_id": "evid-171-001",
            "evidence_digest": hashlib.sha256(b"multi_sensor_evidence").hexdigest(),
            "device_id": "ego-link-001",
            "boot_count": 171,
            "timestamp_monotonic_ns": 123456789000,
            "timestamp_utc": "2026-09-19T03:37:00.000Z",
            "window_duration_ms": 1000,
            "imu_evidence": {
                "sample_count": 20,
                "sample_rate_hz": 20.0,
                "motion_rms_m_s2": 0.157,
                "peak_accel_m_s2": 0.312,
                "gyro_variance_dps2": 0.05,
                "is_mock": False,
            },
            "location_evidence": {
                "fix_valid": True,
                "latitude_deg": 22.5431,
                "longitude_deg": 114.0579,
                "hdop": 1.2,
                "ground_speed_m_s": 0.0,
                "satellites_in_use": 14,
                "course_over_ground_deg": 0.0,
            },
            "network_evidence": {
                "network_type": "lte",
                "lte_rsrp_dbm": -88.0,
                "lte_cell_id": "460-00-12345-67",
                "wifi_ap_count": 4,
                "wifi_fingerprint_hash": hashlib.sha256(b"wifi_aps").hexdigest(),
            },
            "power_evidence": {
                "battery_soc_percent": 98.5,
                "battery_voltage_mv": 4210,
                "is_charging": False,
            },
            "provenance": {
                "source_driver_backend": "qmi8658_max17048_sim7670g",
                "firmware_version": "0.1.0-sensor-policy-continuous-021",
                "firmware_elf_sha256": "2411325042246be77f9e696f9d1cc7c89840f97e46fc4a7b5c928bc7c1d39e87",
            },
        }

        state_summary = {
            "contract_version": "egolink.ego_state_estimation.v0.1",
            "estimation_id": "est-001",
            "device_id": "ego-link-001",
            "boot_count": 171,
            "timestamp_monotonic_ns": 123456789000,
            "timestamp_utc": "2026-09-19T03:37:00.000Z",
            "spatial_mobility": "stationary",
            "posture_anomaly": "normal",
            "device_wear_state": "tabletop_resting",
            "confidence": 0.98,
            "window_duration_ms": 1000,
            "reason_codes": ["motion_rms_below_threshold", "gnss_speed_zero"],
            "primary_evidence_digest": evidence["evidence_digest"],
            "is_mock": False,
        }

        report = {
            "contract_version": "egolink.ego_state_report.v0.1",
            "report_id": "rep-171-001",
            "device_id": "ego-link-001",
            "boot_count": 171,
            "session_id": "session-171",
            "report_type": "periodic_aggregate",
            "generated_at_utc": "2026-09-19T03:37:01.000Z",
            "start_monotonic_ns": 122456789000,
            "end_monotonic_ns": 123456789000,
            "state_summary": state_summary,
            "evidence_chain": evidence,
            "privacy_boundary": {
                "local_priority": True,
                "encrypted_at_rest": True,
                "retention_category": "daily_local",
            },
            "notes": ["Bench continuous calibration run"],
        }

        validator.validate(report)

        # Ensure local_priority=False is rejected
        bad_report = dict(report, privacy_boundary={"local_priority": False, "encrypted_at_rest": True, "retention_category": "daily_local"})
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(bad_report)


if __name__ == "__main__":
    unittest.main()
