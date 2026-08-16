from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator

from pc_simulator import imu_six_face_calibration as calibration
from quality_tests import test_imu_window_export as window_export
from scripts import export_imu_windows
from server import message_hub


ROLE_BASE_ACCEL = {
    "x_positive": [1070, -30, 20],
    "x_negative": [-970, -30, 20],
    "y_positive": [50, 950, 20],
    "y_negative": [50, -1010, 20],
    "z_positive": [50, -30, 1025],
    "z_negative": [50, -30, -985],
    "gyro_stationary": [50, -30, 1025],
}
GYRO_BIAS = [120, -250, 75]
BOOT_COUNT = 7


def fixture_capture_cmd_id(role_index: int) -> str:
    return f"cmd-a0001-{role_index:02d}"


def fixture_window_id(role_index: int, *, boot_count: int = BOOT_COUNT) -> str:
    """Mirror the wire contract: window_id == imuw-<capture_cmd_id>-b<boot_count>."""
    return f"imuw-{fixture_capture_cmd_id(role_index)}-b{boot_count}"


def fixture_metadata() -> dict:
    return {
        "schema_version": calibration.METADATA_SCHEMA_VERSION,
        "calibration_run_id": "A0-001-SYNTHETIC-001",
        "calibration_time_utc": "2026-08-16T00:00:00Z",
        "calibration_time_source": "operator_provided_utc",
        "device_id": "ego-link-test-device-001",
        "board_id": "connectivity-node-test-001",
        "hardware_revision": "synthetic-unverified",
        "hardware_profile": "synthetic-qmi8658-contract-fixture",
        "mounting_profile_id": "sensor-axis-six-face-fixture-v0.1",
        "body_axis_mapping_status": "unrecorded",
        "imu_model": "QMI8658A",
        "imu_module": "ATK-NB018 V1.0",
        "sensor_i2c_address": 106,
        "test_run_id": "A0-001-SYNTHETIC-001",
        "firmware": {
            "fw_version": "synthetic-fw-test-only",
            "firmware_commit": "1" * 40,
            "firmware_image_sha256": "2" * 64,
        },
        "calibration_software_commit": "3" * 40,
        "temperature_status": "unavailable_in_imu_window_v1",
        "source_windows": {
            role: fixture_window_id(index) for index, role in enumerate(calibration.SOURCE_ROLES)
        },
    }


def fixture_samples(role: str, role_index: int) -> list[dict]:
    base_accel = ROLE_BASE_ACCEL[role]
    samples = []
    for index in range(calibration.SAMPLE_COUNT):
        accel = [
            base_accel[axis] + ((index + role_index + axis) % 5) - 2
            for axis in range(3)
        ]
        gyro = [
            GYRO_BIAS[axis] + ((index + (role_index * 2) + axis) % 5) - 2
            for axis in range(3)
        ]
        samples.append(
            {
                "index": index,
                "offset_us": index * calibration.REQUESTED_INTERVAL_US,
                "accel_mg": accel,
                "gyro_mdps": gyro,
            }
        )
    return samples


def fixture_rows(metadata: dict) -> list[dict]:
    rows = []
    for role_index, role in enumerate(calibration.SOURCE_ROLES):
        samples = fixture_samples(role, role_index)
        sample_bytes = calibration.encode_source_samples(
            samples, window_id=metadata["source_windows"][role]
        )
        rows.append(
            {
                "contract_version": calibration.SOURCE_CONTRACT_VERSION,
                "window_id": metadata["source_windows"][role],
                "capture_cmd_id": fixture_capture_cmd_id(role_index),
                "boot_count": BOOT_COUNT,
                "device_id": metadata["device_id"],
                "fw_version": metadata["firmware"]["fw_version"],
                "test_run_id": metadata["test_run_id"],
                "source": "qmi8658_i2c",
                "source_status": "observed",
                "transport_type": "wifi",
                "sensor": {
                    "model": metadata["imu_model"],
                    "i2c_address": metadata["sensor_i2c_address"],
                    "accel_unit": "mg",
                    "gyro_unit": "mdps",
                },
                "capture": {
                    "sample_count": calibration.SAMPLE_COUNT,
                    "requested_interval_us": calibration.REQUESTED_INTERVAL_US,
                    "capture_start_uptime_us": 1_000_000 + role_index,
                    "capture_end_uptime_us": 6_000_000 + role_index,
                    "min_interval_us": calibration.REQUESTED_INTERVAL_US,
                    "mean_interval_us": calibration.REQUESTED_INTERVAL_US,
                    "max_interval_us": calibration.REQUESTED_INTERVAL_US,
                    "deadline_miss_count": 0,
                    "read_failure_count": 0,
                    "mock_sample_count": 0,
                    "cadence_quality_status": "qualified",
                },
                "capture_time_basis": "device_monotonic_uptime_only",
                "training_allowed": False,
                "samples_sha256": hashlib.sha256(sample_bytes).hexdigest(),
                "samples": samples,
            }
        )
    return rows


def canonical_jsonl(rows: list[dict]) -> bytes:
    return b"".join(calibration.stable_json_bytes(row) + b"\n" for row in rows)


class A0ImuCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metadata = fixture_metadata()
        self.rows = fixture_rows(self.metadata)

    def build(self):
        return calibration.build_calibration_outputs(
            copy.deepcopy(self.metadata), copy.deepcopy(self.rows)
        )

    def test_valid_fixture_estimates_and_conforms_to_schemas(self) -> None:
        artifact, windows, calibrated_jsonl, _report = self.build()

        self.assertEqual(artifact["accelerometer"]["bias_mg_xyz"], [50.0, -30.0, 20.0])
        self.assertEqual(
            artifact["accelerometer"]["sensitivity_mg_per_g_xyz"],
            [1020.0, 980.0, 1005.0],
        )
        self.assertEqual(artifact["gyroscope"]["bias_mdps_xyz"], GYRO_BIAS)
        self.assertFalse(artifact["production_ready"])
        self.assertFalse(artifact["training_allowed"])
        self.assertEqual(artifact["calibration_time_source"], "operator_provided_utc")
        self.assertEqual(
            artifact["payload_sha256"], calibration.artifact_payload_sha256(artifact)
        )
        self.assertEqual(
            artifact["materialized_output"]["sha256"], hashlib.sha256(calibrated_jsonl).hexdigest()
        )
        self.assertEqual(len(windows), 7)
        self.assertTrue(
            all(window["calibration_identity_sha256"] == artifact["identity_sha256"] for window in windows)
        )

        artifact_schema = json.loads(calibration.ARTIFACT_SCHEMA_PATH.read_text(encoding="utf-8"))
        window_schema = json.loads(
            calibration.CALIBRATED_WINDOW_SCHEMA_PATH.read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(artifact_schema)
        Draft202012Validator.check_schema(window_schema)
        Draft202012Validator(artifact_schema).validate(artifact)
        for window in windows:
            Draft202012Validator(window_schema).validate(window)

    def test_identity_and_outputs_are_deterministic_and_manifest_bound(self) -> None:
        first = self.build()
        second = self.build()
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[2], second[2])
        self.assertEqual(first[3], second[3])

        changed_metadata = copy.deepcopy(self.metadata)
        changed_metadata["calibration_run_id"] = "A0-001-SYNTHETIC-002"
        changed = calibration.build_calibration_outputs(changed_metadata, copy.deepcopy(self.rows))
        self.assertNotEqual(first[0]["identity_sha256"], changed[0]["identity_sha256"])
        self.assertNotEqual(first[0]["calibration_id"], changed[0]["calibration_id"])

        changed_source_manifest = copy.deepcopy(self.rows)
        changed_source_manifest[0]["_source_export_sha256"] = "f" * 64
        changed_source = calibration.build_calibration_outputs(
            copy.deepcopy(self.metadata), changed_source_manifest
        )
        self.assertNotEqual(first[0]["identity_sha256"], changed_source[0]["identity_sha256"])

    def test_uncalibrated_values_are_preserved_and_calibrated_values_are_added(self) -> None:
        _artifact, windows, _jsonl, _report = self.build()
        by_role = {window["role"]: window for window in windows}
        for role_index, role in enumerate(calibration.SOURCE_ROLES):
            raw = self.rows[role_index]["samples"]
            materialized = by_role[role]["samples"]
            self.assertEqual(
                [sample["uncalibrated"]["accel_mg"] for sample in materialized],
                [sample["accel_mg"] for sample in raw],
            )
            self.assertEqual(
                [sample["uncalibrated"]["gyro_mdps"] for sample in materialized],
                [sample["gyro_mdps"] for sample in raw],
            )
            self.assertIn("accel_m_s2", materialized[0]["calibrated"])
            self.assertIn("gyro_rad_s", materialized[0]["calibrated"])
            self.assertEqual(
                by_role[role]["availability"]["adc_counts"],
                "unavailable_in_imu_window_v1",
            )
            self.assertEqual(
                by_role[role]["availability"]["sample_utc"],
                "unavailable_pending_A0-002",
            )

    def test_missing_face_fails_closed(self) -> None:
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "exactly the seven"):
            calibration.build_calibration_outputs(self.metadata, self.rows[:-1])

    def test_duplicate_window_binding_fails_closed(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["source_windows"]["x_negative"] = metadata["source_windows"]["x_positive"]
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "seven unique windows"):
            calibration.build_calibration_outputs(metadata, self.rows)

    def test_tampered_sample_hash_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["samples"][0]["accel_mg"][0] += 1
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "samples_sha256"):
            calibration.build_calibration_outputs(self.metadata, rows)

    def test_source_mismatch_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["source"] = "simulated"
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "real observed"):
            calibration.build_calibration_outputs(self.metadata, rows)

    def test_mislabeled_face_fails_closed(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["source_windows"]["x_positive"], metadata["source_windows"]["y_positive"] = (
            metadata["source_windows"]["y_positive"],
            metadata["source_windows"]["x_positive"],
        )
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "dominant acceleration axis"):
            calibration.build_calibration_outputs(metadata, self.rows)

    def test_incompatible_cadence_fails_even_with_consistent_hash_and_metadata(self) -> None:
        rows = copy.deepcopy(self.rows)
        row = rows[0]
        for index, sample in enumerate(row["samples"]):
            sample["offset_us"] = index * 70_000
        row["samples_sha256"] = hashlib.sha256(
            calibration.encode_source_samples(row["samples"], window_id=row["window_id"])
        ).hexdigest()
        row["capture"].update(
            min_interval_us=70_000,
            mean_interval_us=70_000,
            max_interval_us=70_000,
            capture_end_uptime_us=row["capture"]["capture_start_uptime_us"] + 7_000_000,
        )
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "20 Hz"):
            calibration.build_calibration_outputs(self.metadata, rows)

    def test_commit_length_and_time_source_are_strict(self) -> None:
        for invalid_commit in ("a" * 41, "b" * 63):
            metadata = copy.deepcopy(self.metadata)
            metadata["firmware"]["firmware_commit"] = invalid_commit
            with self.subTest(length=len(invalid_commit)):
                with self.assertRaisesRegex(calibration.ImuCalibrationError, "invalid format"):
                    calibration.build_calibration_outputs(metadata, self.rows)
        metadata = copy.deepcopy(self.metadata)
        metadata["calibration_time_source"] = "sample_utc"
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "calibration_time_source"):
            calibration.build_calibration_outputs(metadata, self.rows)

    def test_rotating_stationary_window_is_rejected_instead_of_becoming_gyro_bias(self) -> None:
        rows = copy.deepcopy(self.rows)
        gyro_window_id = self.metadata["source_windows"]["gyro_stationary"]
        for row in rows:
            if row["window_id"] != gyro_window_id:
                continue
            for sample in row["samples"]:
                sample["gyro_mdps"][2] += 15_000
            row["samples_sha256"] = hashlib.sha256(
                calibration.encode_source_samples(row["samples"], window_id=row["window_id"])
            ).hexdigest()
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "at least one window was rotating"):
            calibration.build_calibration_outputs(self.metadata, rows)

    def test_rotating_face_window_is_rejected_by_cross_window_gyro_agreement(self) -> None:
        rows = copy.deepcopy(self.rows)
        face_window_id = self.metadata["source_windows"]["y_negative"]
        for row in rows:
            if row["window_id"] != face_window_id:
                continue
            for sample in row["samples"]:
                sample["gyro_mdps"][0] -= 9_000
            row["samples_sha256"] = hashlib.sha256(
                calibration.encode_source_samples(row["samples"], window_id=row["window_id"])
            ).hexdigest()
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "at least one window was rotating"):
            calibration.build_calibration_outputs(self.metadata, rows)

    def test_gyro_agreement_is_recorded_for_every_window(self) -> None:
        artifact, _windows, _jsonl, report = self.build()
        gyroscope = artifact["gyroscope"]
        self.assertEqual(set(gyroscope["window_mean_mdps"]), set(calibration.SOURCE_ROLES))
        self.assertEqual(gyroscope["max_abs_cross_window_delta_mdps"], 0.0)
        self.assertTrue(artifact["quality"]["all_windows_gyro_consistent"])
        self.assertIn("Fit Diagnostics (Not Accuracy)", report)
        self.assertIn("not independent accuracy", report)

    def test_windows_from_more_than_one_boot_fail_closed(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        rows = copy.deepcopy(self.rows)
        other_boot = BOOT_COUNT + 1
        for role_index, role in enumerate(calibration.SOURCE_ROLES):
            if role_index < 4:
                continue
            rows[role_index]["boot_count"] = other_boot
            rows[role_index]["window_id"] = fixture_window_id(role_index, boot_count=other_boot)
            metadata["source_windows"][role] = rows[role_index]["window_id"]
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "must share one device boot"):
            calibration.build_calibration_outputs(metadata, rows)

    def test_window_id_must_derive_from_capture_cmd_id_and_boot_count(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["boot_count"] = BOOT_COUNT + 3
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "not derived from its own"):
            calibration.build_calibration_outputs(self.metadata, rows)

    def test_unfilled_placeholder_provenance_fails_closed(self) -> None:
        for field in ("firmware_commit", "firmware_image_sha256"):
            metadata = copy.deepcopy(self.metadata)
            metadata["firmware"][field] = "0" * len(metadata["firmware"][field])
            with self.subTest(field=field):
                with self.assertRaisesRegex(calibration.ImuCalibrationError, "all-zero placeholder"):
                    calibration.build_calibration_outputs(metadata, self.rows)
        metadata = copy.deepcopy(self.metadata)
        metadata["calibration_software_commit"] = "0" * 40
        with self.assertRaisesRegex(calibration.ImuCalibrationError, "all-zero placeholder"):
            calibration.build_calibration_outputs(metadata, self.rows)

    def test_standard_command_preserves_source_bytes_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            metadata_path = temp_dir / "metadata.json"
            source_path = temp_dir / "imu_windows.jsonl"
            output_dir = temp_dir / "derived"
            metadata_path.write_text(
                json.dumps(self.metadata, ensure_ascii=False, sort_keys=True), encoding="utf-8"
            )
            source_path.write_bytes(canonical_jsonl(self.rows))
            before = source_path.read_bytes()
            before_sha256 = hashlib.sha256(before).hexdigest()

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/generate_a0_imu_calibration.py",
                    "--metadata",
                    str(metadata_path),
                    "--imu-windows",
                    str(source_path),
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
                cwd=calibration.REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertFalse(summary["hardware_gate_passed"])
            self.assertFalse(summary["production_ready"])
            self.assertFalse(summary["training_allowed"])
            self.assertEqual(source_path.read_bytes(), before)
            self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), before_sha256)

            artifact = json.loads(
                (output_dir / "imu_calibration_artifact.json").read_text(encoding="utf-8")
            )
            self.assertEqual(artifact["source_exports"], [{"sha256": before_sha256}])
            materialized = [
                json.loads(line)
                for line in (output_dir / "imu_calibrated_windows.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                materialized[0]["samples"][0]["uncalibrated"]["accel_mg"],
                self.rows[0]["samples"][0]["accel_mg"],
            )


EXPORT_POSE_ACCEL = {
    "x_positive": [1005, 12, -8],
    "x_negative": [-995, 12, -8],
    "y_positive": [5, 1010, -8],
    "y_negative": [5, -990, -8],
    "z_positive": [5, 12, 1002],
    "z_negative": [5, 12, -998],
    "gyro_stationary": [5, 12, 1002],
}
EXPORT_GYRO_BIAS = [40, -60, 25]
EXPORT_BOOT_COUNT = 7


def export_pose_sample_bytes(role: str, role_index: int) -> bytes:
    base = EXPORT_POSE_ACCEL[role]
    payload = bytearray()
    for index in range(message_hub.IMU_WINDOW_SAMPLE_COUNT):
        accel = [base[axis] + ((index + role_index + axis) % 3) - 1 for axis in range(3)]
        gyro = [EXPORT_GYRO_BIAS[axis] + ((index + role_index + axis) % 3) - 1 for axis in range(3)]
        payload.extend((1000 + index * message_hub.IMU_WINDOW_INTERVAL_US).to_bytes(4, "little"))
        for value in [*accel, *gyro]:
            payload.extend(int(value).to_bytes(4, "little", signed=True))
    return bytes(payload)


class A0ImuCalibrationExporterCompatibilityTests(unittest.TestCase):
    """The calibration tool must consume genuine scripts/export_imu_windows.py output."""

    def ingest_pose(self, store, role: str, role_index: int) -> str:
        cmd_id = f"cmd-pose-{role_index}"
        store.create_command(
            window_export.DEVICE_ID,
            {
                "cmd": "capture_imu_window",
                "cmd_id": cmd_id,
                "test_run_id": window_export.TEST_RUN_ID,
                "payload": {"sample_count": 100, "interval_ms": 50},
            },
        )
        samples = export_pose_sample_bytes(role, role_index)
        for index in range(message_hub.IMU_WINDOW_CHUNK_COUNT):
            frame = message_hub.build_raw_frame(
                "event",
                f"imu-{cmd_id}-b{EXPORT_BOOT_COUNT}-c{index:02d}",
                window_export.chunk_payload(
                    index, samples, cmd_id=cmd_id, boot_count=EXPORT_BOOT_COUNT
                ),
                seq=index + 1,
            )
            record = store.ingest_raw_frame(window_export.DEVICE_ID, frame)
            self.assertEqual(record["parse_result"]["status"], "ok", record["parse_result"])
        manifest_frame = message_hub.build_raw_frame(
            "event",
            f"imu-{cmd_id}-b{EXPORT_BOOT_COUNT}-manifest",
            window_export.manifest_payload(samples, cmd_id=cmd_id, boot_count=EXPORT_BOOT_COUNT),
            seq=message_hub.IMU_WINDOW_CHUNK_COUNT + 1,
        )
        record = store.ingest_raw_frame(window_export.DEVICE_ID, manifest_frame)
        self.assertEqual(record["parse_result"]["status"], "ok", record["parse_result"])
        return f"imuw-{cmd_id}-b{EXPORT_BOOT_COUNT}"

    def test_real_export_output_is_accepted_and_bound_without_reshaping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            db_path = temp_dir / "hub.db"
            store = message_hub.MessageHubStore(db_path)
            store.create_test_run({"test_run_id": window_export.TEST_RUN_ID})
            source_windows = {
                role: self.ingest_pose(store, role, role_index)
                for role_index, role in enumerate(calibration.SOURCE_ROLES)
            }
            export_result = export_imu_windows.export_imu_windows(
                db_path,
                temp_dir / "export",
                device_id=window_export.DEVICE_ID,
                test_run_id=window_export.TEST_RUN_ID,
            )
            self.assertTrue(export_result["ok"], export_result["invalid"])
            self.assertEqual(export_result["summary"]["valid_windows"], 7)

            jsonl_path = temp_dir / "export" / "imu_windows.jsonl"
            metadata = fixture_metadata()
            metadata.update(
                calibration_run_id="A0-001-EXPORT-COMPAT-001",
                device_id=window_export.DEVICE_ID,
                test_run_id=window_export.TEST_RUN_ID,
                source_windows=source_windows,
            )
            metadata["firmware"]["fw_version"] = "0.1.0-imu-unit"

            windows = calibration.load_export_windows([jsonl_path])
            artifact, calibrated, _jsonl, _report = calibration.build_calibration_outputs(
                metadata, windows
            )
            # The exported window carries fields the calibration tool does not consume; it
            # must neither require them to be stripped nor silently drop what it does bind.
            exported = {
                row["window_id"]: row
                for row in (
                    json.loads(line)
                    for line in jsonl_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            }

        self.assertEqual(len(calibrated), 7)
        self.assertEqual(
            {row["boot_count"] for row in artifact["source_windows"]}, {EXPORT_BOOT_COUNT}
        )
        self.assertEqual(artifact["capture_profile"]["device_boot_count"], EXPORT_BOOT_COUNT)
        self.assertFalse(artifact["production_ready"])
        self.assertFalse(artifact["training_allowed"])
        for row in artifact["source_windows"]:
            self.assertEqual(
                row["window_id"], f"imuw-{row['capture_cmd_id']}-b{row['boot_count']}"
            )
        by_role = {window["role"]: window for window in calibrated}
        for role, window_id in source_windows.items():
            self.assertEqual(
                [sample["uncalibrated"]["accel_mg"] for sample in by_role[role]["samples"]],
                [sample["accel_mg"] for sample in exported[window_id]["samples"]],
            )
            self.assertEqual(
                by_role[role]["source_window"]["samples_sha256"],
                exported[window_id]["samples_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
