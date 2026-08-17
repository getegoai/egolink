from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pc_simulator import field_session
from pc_simulator import field_session_pack as packer
from pc_simulator import imu_six_face_calibration as calibration
from quality_tests import test_a0_imu_calibration as calibration_fixture


SESSION_ID = "FS-20260817T000000Z-a1b2c3d4e5f6"
FIRMWARE_COMMIT = "1" * 40
FIRMWARE_IMAGE_SHA256 = "2" * 64
REPOSITORY_COMMIT = "4" * 40
JPEG = b"\xff\xd8\xff\xd9"


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_bytes(b"".join(calibration.stable_json_bytes(value) + b"\n" for value in values))


def _clock_sample(index: int, seconds: int, sample_type: str) -> dict:
    return {
        "sample_id": f"clock-{index:06d}",
        "sample_index": index,
        "sample_type": sample_type,
        "timestamp_monotonic_ns": seconds * 1_000_000_000,
        "timestamp_utc": f"2026-08-17T00:{seconds // 60:02d}:{seconds % 60:02d}Z",
        "pairing_span_ns": 1_000_000,
        "time_origin_utc_ms": 1_786_924_800_000,
        "visibility_state": "visible",
        "alignment_status": "estimated_unverified",
    }


def _sidecar_bundle() -> dict:
    media_sha = hashlib.sha256(JPEG).hexdigest()
    event_specs = [
        (0, 20, "START_WALKING"),
        (1, 30, "PUT_IN_BAG"),
        (2, 40, "ENTER_BUILDING"),
        (3, 50, "EXIT_BUILDING"),
        (5, 70, "STOP"),
    ]
    records: list[dict] = []
    for sequence, seconds, event_type in event_specs:
        records.append(
            {
                "record_type": "manual_event",
                "event_id": f"{SESSION_ID}:event:{sequence:06d}",
                "sequence_id": sequence,
                "source": "manual_event",
                "capture_method": "test_phone",
                "event_type": event_type,
                "timestamp_monotonic_ns": seconds * 1_000_000_000,
                "timestamp_utc": f"2026-08-17T00:{seconds // 60:02d}:{seconds % 60:02d}Z",
                "clock_domain_id": "browser-performance-1786924800000000",
                "clock_sample_id": f"clock-{sequence + 1:06d}",
                "alignment_status": "estimated_unverified",
                "timestamp_uncertainty_ns": 1_000_000,
                "operator_ref": "operator-01",
                "note": None,
                "label_semantics": "weak_operator_event",
            }
        )
    records.append(
        {
            "record_type": "camera",
            "observation_id": f"{SESSION_ID}:camera:000004",
            "sequence_id": 4,
            "source": "camera",
            "capture_method": "test_phone",
            "timestamp_monotonic_ns": 60_000_000_000,
            "timestamp_utc": "2026-08-17T00:01:00Z",
            "clock_domain_id": "browser-performance-1786924800000000",
            "clock_sample_id": "clock-000005",
            "alignment_status": "estimated_unverified",
            "timestamp_uncertainty_ns": 1_000_000,
            "timestamp_semantics": "capture_return",
            "media_path": "camera/000004.jpg",
            "media_sha256": media_sha,
            "media_size_bytes": len(JPEG),
            "reason_codes": ["browser_file_input_has_no_exposure_timestamp"],
        }
    )
    records.sort(key=lambda row: row["sequence_id"])
    samples = [_clock_sample(0, 10, "start")]
    for sequence, seconds in enumerate((20, 30, 40, 50, 60, 70), start=1):
        samples.append(_clock_sample(sequence, seconds, "camera_capture_return" if seconds == 60 else "manual_event"))
    acknowledged = "2026-08-17T00:00:10Z"
    return {
        "format_version": packer.SIDECAR_VERSION,
        "bundle_role": "a0_003_adapter_input",
        "gate_status": "unverified",
        "status": "stopped",
        "session": {
            "session_id": SESSION_ID,
            "operator_ref": "operator-01",
            "capture_start_utc": "2026-08-17T00:00:10Z",
            "capture_end_utc": "2026-08-17T00:01:10Z",
        },
        "producer": {
            "source": "test_phone",
            "device_id": "field-phone-001",
            "device_run_id": f"{SESSION_ID}:sidecar:0",
            "clock_domain_id": "browser-performance-1786924800000000",
            "clock_kind": "browser_performance",
        },
        "clock": {
            "alignment_status": "estimated_unverified",
            "time_origin_utc_ms": 1_786_924_800_000,
            "time_origin_utc": "2026-08-17T00:00:00Z",
            "first_sample_id": samples[0]["sample_id"],
            "last_sample_id": samples[-1]["sample_id"],
            "samples": samples,
            "visibility_events": [],
            "discontinuity": None,
        },
        "privacy": {
            "local_only": True,
            "network_upload": False,
            "raw_image_allowed": True,
            "raw_image_capture_acknowledged": True,
            "acknowledged_at_utc": acknowledged,
            "training_allowed": False,
            "consent_acknowledgement": {
                "acknowledged": True,
                "operator_ref": "operator-01",
                "acknowledged_at_utc": acknowledged,
                "scope": "local_engineering_private_jpeg",
                "statements": [
                    "small_bounded_jpeg_capture",
                    "local_private_storage_only",
                    "must_not_commit_to_git",
                    "training_not_allowed",
                ],
            },
            "retention_acknowledgement": {
                "acknowledged": True,
                "operator_ref": "operator-01",
                "acknowledged_at_utc": acknowledged,
                "status": "post_experiment_review_required",
            },
            "control_plane_approval": False,
            "gate_approval": False,
        },
        "records": records,
        "media": [
            {
                "path": "camera/000004.jpg",
                "media_type": "image/jpeg",
                "sha256": media_sha,
                "size_bytes": len(JPEG),
                "data_base64": base64.b64encode(JPEG).decode("ascii"),
            }
        ],
        "limits": {
            "max_bundle_bytes": 4 * 1024 * 1024,
            "max_input_jpeg_bytes": 12 * 1024 * 1024,
            "max_jpeg_bytes": 512 * 1024,
            "max_photo_count": 6,
            "max_total_jpeg_bytes": 2 * 1024 * 1024,
        },
        "limitations": ["test fixture"],
    }


def _fixture(root: Path) -> dict:
    metadata = calibration_fixture.fixture_metadata()
    raw_calibration_rows = calibration_fixture.fixture_rows(metadata)
    source_bytes = calibration_fixture.canonical_jsonl(raw_calibration_rows)
    calibration_input = copy.deepcopy(raw_calibration_rows)
    for row in calibration_input:
        row["_source_export_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    artifact, _windows, _jsonl, _report = calibration.build_calibration_outputs(
        copy.deepcopy(metadata), calibration_input
    )
    field_imu = copy.deepcopy(raw_calibration_rows[0])
    field_imu["server_received_at_first"] = "2026-08-17T00:00:30Z"
    field_imu["server_received_at_last"] = "2026-08-17T00:00:31Z"
    field_export = {
        "test_run": {
            "test_run_id": "field-window-fixture",
            "status": "bounded_export",
            "device_id": metadata["device_id"],
            "started_at": "2026-08-17T00:00:00Z",
            "ended_at": "2026-08-17T00:02:00Z",
            "created_at": "2026-08-17T00:02:01Z",
        },
        "messages": [
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": metadata["device_id"],
                "message_type": "status",
                "seq": 1,
                "ts": "uptime_ms:500",
                "server_received_at": "2026-08-17T00:00:05Z",
                "fw_version": metadata["firmware"]["fw_version"],
                "boot_count": calibration_fixture.BOOT_COUNT,
            },
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": metadata["device_id"],
                "message_type": "event",
                "event_type": "location_report",
                "seq": 10,
                "ts": "uptime_ms:10000",
                "server_received_at": "2026-08-17T00:00:20Z",
                "fw_version": metadata["firmware"]["fw_version"],
                "test_run_id": "field-source-fixture",
                "source": "sim7670g_firmware_gnss",
                "source_status": "observed",
                "fix": True,
                "lat": 22.5,
                "lon": 114.0,
                "utc_date": "170826",
                "utc_time": "000010.000",
            },
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": metadata["device_id"],
                "message_type": "event",
                "event_type": "location_observation",
                "seq": 11,
                "ts": "raw_frame:obs-fixture",
                "server_received_at": "2026-08-17T00:00:21Z",
                "fw_version": metadata["firmware"]["fw_version"],
                "test_run_id": "field-source-fixture",
                "cell": {"mcc": "460", "mnc": "01", "cell_id": "1001", "rsrp": -90},
                "lte": {"registration": "registered"},
            },
            {
                "protocol_version": "egolink.p0.v1",
                "device_id": metadata["device_id"],
                "message_type": "event",
                "event_type": "location_report",
                "seq": 12,
                "ts": "raw_frame:gnss-fixture",
                "server_received_at": "2026-08-17T00:00:22Z",
                "fw_version": metadata["firmware"]["fw_version"],
                "test_run_id": "field-source-fixture",
                "source": "sim7670g_firmware_gnss",
                "source_status": "observed",
                "fix": True,
                "lat": 22.5001,
                "lon": 114.0001,
                "utc_date": "170826",
                "utc_time": "000012.000",
            },
        ],
        "commands": [],
        "raw_frames": [],
        "window": {
            "mode": "device_server_received_time",
            "device_id": metadata["device_id"],
            "started_at": "2026-08-17T00:00:00Z",
            "ended_at": "2026-08-17T00:02:00Z",
            "duration_s": 120,
            "max_records_per_collection": 100,
            "returned": {"messages": 4, "commands": 0, "raw_frames": 0},
            "truncated": {"messages": False, "commands": False, "raw_frames": False},
            "complete": True,
            "privacy_boundary": "test fixture",
        },
        "observability_summary": {},
        "run_context": {},
    }
    paths = {
        "field": root / "field-export.json",
        "imu": root / "imu-windows.jsonl",
        "calibration": root / "calibration.json",
        "sidecar": root / "sidecar.json",
        "output": root / "package",
        "field_value": field_export,
        "imu_value": [field_imu],
        "calibration_value": artifact,
        "sidecar_value": _sidecar_bundle(),
    }
    _write_json(paths["field"], field_export)
    _write_jsonl(paths["imu"], [field_imu])
    _write_json(paths["calibration"], artifact)
    _write_json(paths["sidecar"], paths["sidecar_value"])
    return paths


def _pack(paths: dict, output_name: str = "package") -> dict:
    return packer.pack_field_session(
        field_export_path=paths["field"],
        imu_windows_path=paths["imu"],
        calibration_artifact_path=paths["calibration"],
        sidecar_bundle_path=paths["sidecar"],
        output_dir=paths["field"].parent / output_name,
        test_scenario="outdoor stationary to indoor walking and outdoor end",
        firmware_commit=FIRMWARE_COMMIT,
        firmware_image_sha256=FIRMWARE_IMAGE_SHA256,
        repository_commit=REPOSITORY_COMMIT,
    )


def _run_cli(paths: dict, output_name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/pack_field_session.py",
            "--field-export", str(paths["field"]),
            "--imu-windows", str(paths["imu"]),
            "--calibration-artifact", str(paths["calibration"]),
            "--sidecar-bundle", str(paths["sidecar"]),
            "--output-dir", str(paths["field"].parent / output_name),
            "--test-scenario", "fixture",
            "--firmware-commit", FIRMWARE_COMMIT,
            "--firmware-image-sha256", FIRMWARE_IMAGE_SHA256,
            "--repository-commit", REPOSITORY_COMMIT,
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


class FieldSessionPackTests(unittest.TestCase):
    def test_exact_inputs_create_valid_sealed_engineering_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            result = _pack(paths)
            manifest = field_session.load_json(root / "package/manifest.json")
            raw_rows = field_session.load_jsonl(root / "package/streams/imu-raw.jsonl")
            calibrated_rows = field_session.load_jsonl(root / "package/streams/imu-calibrated.jsonl")
            gnss_rows = field_session.load_jsonl(root / "package/streams/gnss.jsonl")
            lte_rows = field_session.load_jsonl(root / "package/streams/lte.jsonl")
            time_rows = field_session.load_jsonl(root / "package/time/time-records.jsonl")
            gnss_artifact_sha256 = next(
                item["sha256"] for item in manifest["artifacts"] if item["artifact_id"] == "stream-gnss"
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence_scope"], "engineering_smoke_only")
        self.assertEqual(result["gate_status"], "unverified")
        self.assertEqual(result["time_status"]["gnss"], "direct_source_utc_unaligned")
        self.assertEqual(result["time_status"]["lte"], "receive_only")
        self.assertFalse(result["validation"]["field_eligible"])
        self.assertFalse(result["validation"]["a0_002_time_lineage"]["field_eligible"])
        for field in (
            "manifest_file_binding_verified",
            "artifact_integrity_verified",
            "package_closure_verified",
            "imu_raw_calibrated_chain_verified",
            "a0_002_report_binding_verified",
        ):
            self.assertTrue(result["validation"][field], field)
        self.assertEqual(manifest["lifecycle_state"], "complete")
        self.assertEqual(manifest["seal"]["status"], "sealed")
        self.assertEqual(len(raw_rows), len(calibrated_rows))
        self.assertEqual(len(raw_rows[0]["samples"]), len(calibrated_rows[0]["samples"]))
        self.assertEqual(gnss_rows, [paths["field_value"]["messages"][1], paths["field_value"]["messages"][3]])
        self.assertEqual(lte_rows, [paths["field_value"]["messages"][2]])
        direct_gnss = [
            row
            for row in time_rows
            if row["source"] == "gnss" and row["alignment"]["timestamp_utc_origin"] == "source_timestamp"
        ]
        self.assertEqual([row["timestamp_utc"] for row in direct_gnss], [
            "2026-08-17T00:00:10Z",
            "2026-08-17T00:00:12Z",
        ])
        for row in direct_gnss:
            self.assertEqual(row["alignment"]["status"], "unavailable")
            self.assertIsNone(row["timestamp_monotonic_ns"])
            self.assertIsNone(row["monotonic_clock_domain_id"])
            self.assertIsNone(row["boot_count"])
            self.assertEqual(row["source_timestamp"]["source_field"], "message.utc_date+utc_time")
            self.assertEqual(row["lineage"]["source_record_sha256"], gnss_artifact_sha256)
        self.assertFalse(manifest["privacy"]["training_allowed"])
        self.assertIn("A-R0 remain unverified", " ".join(manifest["limitations"]))

    def test_missing_empty_malformed_and_unknown_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            paths["imu"].write_bytes(b"")
            with self.assertRaisesRegex(packer.FieldSessionPackError, "must not be empty"):
                _pack(paths, "empty")

            paths = _fixture(root)
            paths["imu"].write_text('{"broken":\n', encoding="utf-8")
            with self.assertRaisesRegex(packer.FieldSessionPackError, "invalid JSON"):
                _pack(paths, "malformed")

            paths = _fixture(root)
            sidecar = paths["sidecar_value"]
            sidecar["records"][0]["record_type"] = "mystery"
            _write_json(paths["sidecar"], sidecar)
            with self.assertRaisesRegex(packer.FieldSessionPackError, "unknown record_type"):
                _pack(paths, "unknown")

            paths = _fixture(root)
            paths["field_value"]["messages"] = paths["field_value"]["messages"][:2]
            paths["field_value"]["window"]["returned"]["messages"] = 2
            _write_json(paths["field"], paths["field_value"])
            with self.assertRaisesRegex(packer.FieldSessionPackError, "no LTE"):
                _pack(paths, "missing-lte")

    def test_calibration_nan_missing_axis_and_unit_conflicts_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            text = paths["calibration"].read_text(encoding="utf-8").replace(
                '"bias_mg_xyz": [', '"bias_mg_xyz": [NaN,', 1
            )
            paths["calibration"].write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(packer.FieldSessionPackError, "non-finite"):
                _pack(paths, "nan")

            paths = _fixture(root)
            artifact = paths["calibration_value"]
            artifact["accelerometer"]["bias_mg_xyz"] = artifact["accelerometer"]["bias_mg_xyz"][:2]
            _write_json(paths["calibration"], artifact)
            with self.assertRaisesRegex(packer.FieldSessionPackError, "too short"):
                _pack(paths, "axis")

            paths = _fixture(root)
            artifact = paths["calibration_value"]
            artifact["sensor"]["uncalibrated_accel_unit"] = "m_s2"
            _write_json(paths["calibration"], artifact)
            with self.assertRaisesRegex(packer.FieldSessionPackError, "mg"):
                _pack(paths, "unit")

    def test_media_hash_identity_time_privacy_and_commit_conflicts_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            paths["sidecar_value"]["media"][0]["sha256"] = "0" * 64
            _write_json(paths["sidecar"], paths["sidecar_value"])
            with self.assertRaisesRegex(packer.FieldSessionPackError, "SHA-256 mismatch"):
                _pack(paths, "hash")

            paths = _fixture(root)
            paths["sidecar_value"]["producer"]["device_run_id"] = "other-sidecar-run"
            _write_json(paths["sidecar"], paths["sidecar_value"])
            with self.assertRaisesRegex(packer.FieldSessionPackError, "device_run_id"):
                _pack(paths, "id")

            paths = _fixture(root)
            paths["sidecar_value"]["records"][0]["timestamp_utc"] = "2026-08-17T00:01:59Z"
            _write_json(paths["sidecar"], paths["sidecar_value"])
            with self.assertRaisesRegex(packer.FieldSessionPackError, "outside the sidecar"):
                _pack(paths, "time")

            paths = _fixture(root)
            paths["sidecar_value"]["privacy"]["retention_acknowledgement"]["acknowledged"] = False
            _write_json(paths["sidecar"], paths["sidecar_value"])
            with self.assertRaisesRegex(packer.FieldSessionPackError, "privacy"):
                _pack(paths, "privacy")

            paths = _fixture(root)
            paths["field_value"]["messages"][1]["firmware_commit"] = "f" * 40
            _write_json(paths["field"], paths["field_value"])
            with self.assertRaisesRegex(packer.FieldSessionPackError, "conflicts with the CLI"):
                _pack(paths, "commit")

    def test_manual_event_order_and_clock_sample_binding_fail_closed(self) -> None:
        cases = (
            (
                "event-order",
                lambda bundle: (
                    bundle["records"][0].__setitem__("event_type", "PUT_IN_BAG"),
                    bundle["records"][1].__setitem__("event_type", "START_WALKING"),
                ),
                "exactly once in order",
            ),
            (
                "event-duplicate",
                lambda bundle: bundle["records"][1].__setitem__("event_type", "START_WALKING"),
                "exactly once in order",
            ),
            (
                "clock-monotonic",
                lambda bundle: bundle["records"][0].__setitem__("timestamp_monotonic_ns", 20_000_000_001),
                "exactly match its clock sample",
            ),
            (
                "clock-utc",
                lambda bundle: bundle["records"][0].__setitem__("timestamp_utc", "2026-08-17T00:00:21Z"),
                "exactly match its clock sample",
            ),
            (
                "clock-type",
                lambda bundle: bundle["clock"]["samples"][1].__setitem__("sample_type", "camera_capture_return"),
                "exactly match its clock sample",
            ),
            (
                "clock-uncertainty",
                lambda bundle: bundle["records"][0].__setitem__("timestamp_uncertainty_ns", 999_999),
                "timestamp uncertainty is invalid",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mutate, error_pattern in cases:
                with self.subTest(name=name):
                    case_root = root / name
                    case_root.mkdir()
                    paths = _fixture(case_root)
                    mutate(paths["sidecar_value"])
                    _write_json(paths["sidecar"], paths["sidecar_value"])
                    with self.assertRaisesRegex(packer.FieldSessionPackError, error_pattern):
                        _pack(paths)

    def test_media_paths_reject_windows_and_traversal_escapes(self) -> None:
        for case_name, unsafe_path in (
            ("backslash", "camera\\escape.jpg"),
            ("drive", "C:\\escape.jpg"),
            ("traversal", "camera/../escape.jpg"),
        ):
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as tmp:
                paths = _fixture(Path(tmp))
                paths["sidecar_value"]["media"][0]["path"] = unsafe_path
                paths["sidecar_value"]["records"][4]["media_path"] = unsafe_path
                _write_json(paths["sidecar"], paths["sidecar_value"])
                with self.assertRaisesRegex(packer.FieldSessionPackError, "path is unsafe"):
                    _pack(paths)

    def test_field_export_envelope_counts_and_boot_evidence_fail_closed(self) -> None:
        cases = (
            (
                "truncated-missing",
                lambda export: export["window"]["truncated"].pop("commands"),
                "truncated must contain exactly",
            ),
            (
                "truncated-true",
                lambda export: export["window"]["truncated"].__setitem__("raw_frames", True),
                "truncated must contain exactly",
            ),
            (
                "collection-not-list",
                lambda export: export.__setitem__("commands", {}),
                "must all be arrays",
            ),
            (
                "returned-mismatch",
                lambda export: export["window"]["returned"].__setitem__("messages", 99),
                "returned counts must exactly match",
            ),
            (
                "returned-bool",
                lambda export: export["window"]["returned"].__setitem__("commands", False),
                "returned counts must exactly match",
            ),
            (
                "boot-missing",
                lambda export: export["messages"][0].pop("boot_count"),
                "no explicit boot_count",
            ),
            (
                "boot-conflict",
                lambda export: export["messages"][1].__setitem__("boot_count", calibration_fixture.BOOT_COUNT + 1),
                "boot_count conflicts",
            ),
            (
                "boot-malformed",
                lambda export: export["messages"][0].__setitem__("boot_count", "7"),
                "boot_count must be a non-negative integer",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mutate, error_pattern in cases:
                with self.subTest(name=name):
                    case_root = root / name
                    case_root.mkdir()
                    paths = _fixture(case_root)
                    mutate(paths["field_value"])
                    _write_json(paths["field"], paths["field_value"])
                    with self.assertRaisesRegex(packer.FieldSessionPackError, error_pattern):
                        _pack(paths)

    def test_imu_capture_lineage_prevalidation_and_cli_error_are_clean(self) -> None:
        cases = (
            (
                "capture-time-basis",
                lambda row: row.__setitem__("capture_time_basis", "server_receive_time"),
                "capture_time_basis",
            ),
            (
                "capture-cmd-id",
                lambda row: row.pop("capture_cmd_id"),
                "capture_cmd_id",
            ),
            (
                "transport-type",
                lambda row: row.__setitem__("transport_type", "serial"),
                "transport_type",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, mutate, error_pattern in cases:
                with self.subTest(name=name):
                    case_root = root / name
                    case_root.mkdir()
                    paths = _fixture(case_root)
                    mutate(paths["imu_value"][0])
                    _write_jsonl(paths["imu"], paths["imu_value"])
                    with self.assertRaisesRegex(packer.FieldSessionPackError, error_pattern):
                        _pack(paths)

            cli_root = root / "cli"
            cli_root.mkdir()
            paths = _fixture(cli_root)
            paths["imu_value"][0]["capture_time_basis"] = "server_receive_time"
            _write_jsonl(paths["imu"], paths["imu_value"])
            completed = _run_cli(paths, "invalid")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("capture_time_basis", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_package_tamper_and_cli_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            result = _pack(paths)
            manifest_path = Path(result["manifest"])
            manifest = field_session.load_json(manifest_path)
            camera_path = root / "package/media/camera/000004.jpg"
            camera_path.write_bytes(JPEG + b"tamper")
            validation = field_session.validate_field_session(
                manifest,
                session_root=root / "package",
                manifest_path=manifest_path,
                generated_at="2026-08-17T00:02:00Z",
            )
            self.assertFalse(validation["valid"])
            self.assertIn("artifact_hash_mismatch", {item["code"] for item in validation["errors"]})

            completed = _run_cli(paths, "package")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("refusing to overwrite", completed.stderr)


if __name__ == "__main__":
    unittest.main()
