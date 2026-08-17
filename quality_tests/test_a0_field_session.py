from __future__ import annotations

import copy
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from pc_simulator import field_session
from pc_simulator import imu_six_face_calibration as imu_calibration
from pc_simulator import sensor_time_lineage as time_lineage
from quality_tests import test_a0_imu_calibration as imu_fixture


SESSION_ID = "FS-20260817T000000Z-a0a0a0a0a0a0"
DEVICE_ID = "ego-link-fixture-001"
DEVICE_RUN_ID = "ego-link-fixture-001-boot7"
CLOCK_DOMAIN_ID = "connectivity-boot7-uptime"
FIRMWARE_COMMIT = "1" * 40
SOFTWARE_COMMIT = "2" * 40
GENERATED_AT = "2026-08-17T00:09:00Z"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def _artifact(
    root: Path,
    *,
    artifact_id: str,
    relative_path: str,
    role: str,
    format_name: str,
    media_type: str,
    contract: str | None,
    privacy_class: str,
    record_count: int | None,
) -> dict:
    path = root / Path(relative_path)
    return {
        "artifact_id": artifact_id,
        "path": relative_path,
        "role": role,
        "format": format_name,
        "sha256": field_session.sha256_file(path),
        "size_bytes": path.stat().st_size,
        "record_count": record_count,
        "media_type": media_type,
        "content_contract_version": contract,
        "privacy_class": privacy_class,
        "part_group": None,
        "part_index": None,
        "part_count": None,
    }


def _refresh_artifact(manifest: dict, root: Path, artifact_id: str) -> None:
    artifact = next(item for item in manifest["artifacts"] if item["artifact_id"] == artifact_id)
    path = root / artifact["path"]
    artifact["sha256"] = field_session.sha256_file(path)
    artifact["size_bytes"] = path.stat().st_size
    if artifact["format"] == "jsonl":
        artifact["record_count"] = len(field_session.load_jsonl(path))


def _mapping(root: Path, anchor_artifacts: list[dict]) -> dict:
    mapping = {
        "contract_version": time_lineage.CLOCK_MAPPING_VERSION,
        "mapping_id": "map-boot7-v1",
        "device_id": DEVICE_ID,
        "monotonic_clock_domain_id": CLOCK_DOMAIN_ID,
        "boot_count": 7,
        "monotonic_origin_ns": 1_000_000,
        "utc_origin": "2026-08-17T00:00:00Z",
        "utc_rate_correction_ppm": 0,
        "valid_from_monotonic_ns": 1_000_000,
        "valid_through_monotonic_ns": 10_000_000_000,
        "anchor_method": "fixture_two_point",
        "anchors": [],
        "anchor_count": 2,
        "fit_rms_error_ns": 0,
        "fit_max_error_ns": 0,
        "uncertainty_ns": 5_000,
        "status": "verified",
        "created_at": "2026-08-17T00:08:00Z",
        "lineage": {
            "evidence_scope": "field_session",
            "source_status": "observed",
            "field_session_id": SESSION_ID,
            "firmware_commit": FIRMWARE_COMMIT,
        },
    }
    for index, monotonic_ns in enumerate((1_000_000, 10_000_000_000)):
        artifact = anchor_artifacts[index]
        mapping["anchors"].append(
            {
                "anchor_id": f"map-anchor-{index + 1}",
                "source": "host_clock",
                "timestamp_monotonic_ns": monotonic_ns,
                "timestamp_utc": time_lineage.format_utc_ns(
                    time_lineage.apply_clock_mapping(mapping, monotonic_ns)
                ),
                "uncertainty_ns": 5_000,
                "source_record_ref": artifact["path"],
                "source_record_sha256": artifact["sha256"],
            }
        )
    return mapping


def _time_record(
    source: str,
    index: int,
    mapping: dict,
    stream_artifact: dict,
    anchor: dict,
    *,
    sequence_id: int = 1,
    source_value_us: int | None = None,
    imu_window: dict | None = None,
) -> dict:
    source_value_us = source_value_us if source_value_us is not None else 2_000 + index
    monotonic_ns = source_value_us * 1_000
    semantics = {
        "gnss": "measurement_time",
        "lte": "modem_event_time",
        "imu": "sample_time",
        "camera": "exposure_center",
    }[source]
    imu_derivation = None
    if source == "imu":
        imu_derivation = {
            "method": "capture_start_uptime_us_plus_offset_us",
            "window_id": imu_window["window_id"] if imu_window is not None else "imu-window-fixture-001",
            "capture_start_uptime_us": imu_window["capture"]["capture_start_uptime_us"] if imu_window is not None else 1_000,
            "capture_end_uptime_us": imu_window["capture"]["capture_end_uptime_us"] if imu_window is not None else 5_000,
            "offset_us": 0 if imu_window is not None else source_value_us - 1_000,
        }
    return {
        "contract_version": time_lineage.TIME_LINEAGE_VERSION,
        "observation_id": f"obs-{source}-{sequence_id:03d}",
        "device_id": DEVICE_ID,
        "source": source,
        "stream_id": f"{source}-primary",
        "sequence_id": sequence_id,
        "monotonic_clock_domain_id": CLOCK_DOMAIN_ID,
        "boot_count": 7,
        "timestamp_monotonic_ns": monotonic_ns,
        "timestamp_utc": time_lineage.format_utc_ns(
            time_lineage.apply_clock_mapping(mapping, monotonic_ns)
        ),
        "source_timestamp": {
            "raw_value": source_value_us,
            "unit": "us",
            "clock_domain_id": CLOCK_DOMAIN_ID,
            "semantics": semantics,
            "source_field": f"fixture.{source}.source_uptime_us",
        },
        "receive_timestamp_utc": "2026-08-17T00:00:05Z",
        "ingest_timestamp_utc": "2026-08-17T00:00:06Z",
        "alignment": {
            "status": "verified",
            "timestamp_monotonic_origin": "source_timestamp",
            "monotonic_source_field": f"fixture.{source}.source_uptime_us",
            "timestamp_utc_origin": "clock_mapping",
            "mapping_id": mapping["mapping_id"],
            "anchor": {
                "anchor_id": "shared-capture-anchor-001",
                "method": "fixture_simultaneous_capture",
                "evidence_ref": anchor["path"],
                "evidence_sha256": anchor["sha256"],
            },
            "uncertainty_ns": 5_000,
            "reason_codes": [],
        },
        "lineage": {
            "evidence_scope": "field_session",
            "source_status": "observed",
            "field_session_id": SESSION_ID,
            "test_run_id": "A0-003-SYNTHETIC-TEST-ONLY",
            "firmware_version": "fixture-only",
            "firmware_commit": FIRMWARE_COMMIT,
            "source_record_ref": stream_artifact["path"],
            "source_record_sha256": stream_artifact["sha256"],
        },
        "imu_sample_derivation": imu_derivation,
    }


def _set_stream(
    manifest: dict,
    *,
    stream_id: str,
    source: str,
    artifact: dict,
    contract: str,
    bounds: dict,
    variant: str = "normalized_observation",
    clock_domain_id: str | None = CLOCK_DOMAIN_ID,
    observation_count: int = 1,
) -> dict:
    stream = next(item for item in manifest["streams"] if item["source"] == source)
    stream.update(
        {
            "stream_id": stream_id,
            "variant": variant,
            "status": "captured",
            "format": "jsonl",
            "record_contract_version": contract,
            "artifact_id": artifact["artifact_id"],
            "observation_count": observation_count,
            "device_run_id": DEVICE_RUN_ID,
            "clock_domain_id": clock_domain_id,
            "bounds": bounds,
            "raw_preserved": True,
            "calibration_id": None,
            "source_stream_id": None,
            "generator": None,
            "reason_codes": [],
        }
    )
    return stream


def _build_field_bundle(root: Path, *, sealed: bool = True) -> dict:
    manifest = field_session.build_draft_manifest(
        device_id=DEVICE_ID,
        operator_ref="operator-fixture",
        protocol_id="A0-003-SYNTHETIC-PROTOCOL",
        test_scenario="synthetic contract test only",
        route_id="R-SYNTHETIC",
        created_at_utc="2026-08-17T00:10:00Z",
        session_id=SESSION_ID,
    )
    manifest["lifecycle_state"] = "complete"
    manifest["capture_interval"] = {
        "start_utc": "2026-08-17T00:00:00Z",
        "end_utc": "2026-08-17T00:00:10Z",
        "timezone": "Asia/Shanghai",
    }
    manifest["device_runs"] = [
        {
            "device_run_id": DEVICE_RUN_ID,
            "device_id": DEVICE_ID,
            "role": "primary",
            "board_id": "synthetic-board",
            "hardware_revision": "fixture-only",
            "firmware_version": "fixture-only",
            "firmware_commit": FIRMWARE_COMMIT,
            "firmware_image_sha256": None,
            "boot_count": 7,
            "monotonic_clock_domain_ids": [CLOCK_DOMAIN_ID],
            "source_status": "observed",
        }
    ]
    manifest["software"] = {
        "repository": "egolink",
        "repository_commit": SOFTWARE_COMMIT,
        "capture_tool": "a0-003-fixture",
        "capture_tool_version": "0.1-test-only",
    }
    manifest["scenario"].update(
        {
            "declared_carry_conditions": ["hand"],
            "declared_motion_conditions": ["walking"],
            "declared_environments": ["outdoor_open"],
        }
    )
    manifest["capture_profile"]["protocol_version"] = "fixture-only"
    for source in ("imu", "gnss", "lte", "camera"):
        manifest["sensor_policies"][source].update(
            {
                "mode": "continuous",
                "policy_id": f"fixture-{source}-policy",
                "requested_rate_hz": 20.0 if source == "imu" else 1.0,
            }
        )

    artifacts: list[dict] = []
    for index in (1, 2):
        path = root / f"evidence/map-anchor-{index}.json"
        _write_json(path, {"fixture": True, "anchor_index": index})
        artifacts.append(
            _artifact(
                root,
                artifact_id=f"map-anchor-{index}",
                relative_path=f"evidence/map-anchor-{index}.json",
                role="legacy_attachment",
                format_name="json",
                media_type="application/json",
                contract=None,
                privacy_class="policy_metadata",
                record_count=None,
            )
        )

    calibration_metadata = imu_fixture.fixture_metadata()
    calibration_metadata.update(
        {
            "device_id": DEVICE_ID,
            "board_id": "synthetic-board",
            "hardware_revision": "fixture-only",
            "hardware_profile": "synthetic-contract-fixture",
            "calibration_time_utc": "2026-08-16T00:00:00Z",
            "calibration_software_commit": SOFTWARE_COMMIT,
        }
    )
    calibration_metadata["firmware"] = {
        "fw_version": "fixture-only",
        "firmware_commit": FIRMWARE_COMMIT,
        "firmware_image_sha256": "4" * 64,
    }
    raw_imu_rows = imu_fixture.fixture_rows(calibration_metadata)
    raw_imu_bytes = b"".join(
        imu_calibration.stable_json_bytes(row) + b"\n" for row in raw_imu_rows
    )
    raw_imu_sha256 = hashlib.sha256(raw_imu_bytes).hexdigest()
    calibration_input_rows = copy.deepcopy(raw_imu_rows)
    for row in calibration_input_rows:
        row["_source_export_sha256"] = raw_imu_sha256
    calibration_payload, calibration_pose_rows, _calibration_pose_bytes, _ = (
        imu_calibration.build_calibration_outputs(
            copy.deepcopy(calibration_metadata),
            calibration_input_rows,
        )
    )

    stream_artifacts: dict[str, dict] = {}
    for source in time_lineage.SOURCES:
        relative = f"streams/{source}.jsonl"
        if source == "imu":
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(raw_imu_bytes)
            contract = imu_calibration.SOURCE_CONTRACT_VERSION
            record_count = len(raw_imu_rows)
        else:
            _write_jsonl(root / relative, [{"source": source, "sequence_id": 1, "fixture": True}])
            contract = f"egolink.{source}_observation.fixture.v0.1"
            record_count = 1
        artifact = _artifact(
            root,
            artifact_id=f"stream-{source}",
            relative_path=relative,
            role="stream_data",
            format_name="jsonl",
            media_type="application/x-ndjson",
            contract=contract,
            privacy_class="private_location" if source in {"gnss", "lte", "camera"} else "structured_sensor",
            record_count=record_count,
        )
        artifacts.append(artifact)
        stream_artifacts[source] = artifact

    field_calibrated_rows: list[dict] = []
    for pose_row in calibration_pose_rows:
        source_window = dict(pose_row["source_window"])
        source_window["source_artifact_sha256"] = stream_artifacts["imu"]["sha256"]
        source_window.pop("source_export_sha256")
        field_calibrated_rows.append(
            {
                "schema_version": field_session.IMU_FIELD_CALIBRATED_CONTRACT_VERSION,
                "field_session_id": SESSION_ID,
                "calibration_id": calibration_payload["calibration_id"],
                "calibration_identity_sha256": calibration_payload["identity_sha256"],
                "source_window": source_window,
                "sample_count": pose_row["sample_count"],
                "requested_interval_us": pose_row["requested_interval_us"],
                "training_allowed": False,
                "production_ready": False,
                "availability": {
                    "adc_counts": "unavailable_in_imu_window_v1",
                    "temperature": "unavailable_in_imu_window_v1",
                    "sample_utc": "external_a0_002_time_lineage",
                },
                "samples": copy.deepcopy(pose_row["samples"]),
            }
        )

    mapping = _mapping(root, artifacts[:2])
    records = [
        _time_record(source, index, mapping, stream_artifacts[source], artifacts[0])
        for index, source in enumerate(time_lineage.SOURCES)
        if source != "imu"
    ]
    for sequence_id, window in enumerate(raw_imu_rows, start=1):
        records.append(
            _time_record(
                "imu",
                2,
                mapping,
                stream_artifacts["imu"],
                artifacts[0],
                sequence_id=sequence_id,
                source_value_us=window["capture"]["capture_start_uptime_us"],
                imu_window=window,
            )
        )
    bounds_by_source = {
        source: field_session._observed_bounds(
            [record for record in records if record["source"] == source]
        )
        for source in time_lineage.SOURCES
    }
    for source in time_lineage.SOURCES:
        _set_stream(
            manifest,
            stream_id=f"{source}-primary",
            source=source,
            artifact=stream_artifacts[source],
            contract=stream_artifacts[source]["content_contract_version"],
            bounds=bounds_by_source[source],
            variant="uncalibrated_engineering" if source == "imu" else "normalized_observation",
            observation_count=len(raw_imu_rows) if source == "imu" else 1,
        )

    calibration_path = root / "calibration/imu-calibration.json"
    _write_json(calibration_path, calibration_payload)
    calibration_artifact = _artifact(
        root,
        artifact_id="imu-calibration-artifact",
        relative_path="calibration/imu-calibration.json",
        role="calibration",
        format_name="json",
        media_type="application/json",
        contract=imu_calibration.ARTIFACT_SCHEMA_VERSION,
        privacy_class="structured_sensor",
        record_count=None,
    )
    artifacts.append(calibration_artifact)
    calibrated_path = root / "streams/imu-calibrated.jsonl"
    _write_jsonl(calibrated_path, field_calibrated_rows)
    calibrated_artifact = _artifact(
        root,
        artifact_id="stream-imu-calibrated",
        relative_path="streams/imu-calibrated.jsonl",
        role="stream_data",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=field_session.IMU_FIELD_CALIBRATED_CONTRACT_VERSION,
        privacy_class="structured_sensor",
        record_count=len(field_calibrated_rows),
    )
    artifacts.append(calibrated_artifact)
    manifest["streams"].append(
        {
            "stream_id": "imu-calibrated",
            "source": "imu",
            "variant": "calibrated",
            "status": "captured",
            "format": "jsonl",
            "record_contract_version": calibrated_artifact["content_contract_version"],
            "artifact_id": calibrated_artifact["artifact_id"],
            "observation_count": len(field_calibrated_rows),
            "device_run_id": DEVICE_RUN_ID,
            "clock_domain_id": CLOCK_DOMAIN_ID,
            "bounds": copy.deepcopy(bounds_by_source["imu"]),
            "raw_preserved": True,
            "calibration_id": calibration_payload["calibration_id"],
            "source_stream_id": "imu-primary",
            "generator": {
                "name": "fixture-calibrator",
                "version": "0.1-test-only",
                "commit": SOFTWARE_COMMIT,
                "source_stream_ids": ["imu-primary"],
                "config_artifact_id": "imu-calibration-artifact",
            },
            "reason_codes": [],
        }
    )
    manifest["calibrations"] = [
        {
            "calibration_id": calibration_payload["calibration_id"],
            "sensor": "imu",
            "device_id": DEVICE_ID,
            "status": "engineering",
            "artifact_id": calibration_artifact["artifact_id"],
            "applies_to_stream_ids": ["imu-calibrated"],
        }
    ]

    manual_event = {
        "contract_version": field_session.MANUAL_EVENT_CONTRACT_VERSION,
        "event_id": "event-start-walking-001",
        "session_id": SESSION_ID,
        "sequence_id": 1,
        "event_type": "START_WALKING",
        "capture_method": "device_button",
        "device_run_id": DEVICE_RUN_ID,
        "timestamp_monotonic_ns": None,
        "timestamp_utc": "2026-08-17T00:00:03Z",
        "source_timestamp": {
            "raw_value": "2026-08-17T00:00:03Z",
            "unit": "iso8601",
            "clock_domain_id": "operator-device-utc",
            "source_field": "fixture.button.timestamp_utc",
        },
        "monotonic_clock_domain_id": None,
        "boot_count": None,
        "mapping_id": None,
        "timestamp_uncertainty_ns": 100_000_000,
        "receive_timestamp_utc": "2026-08-17T00:00:03.1Z",
        "ingest_timestamp_utc": "2026-08-17T00:00:03.2Z",
        "alignment_status": "estimated",
        "timestamp_monotonic_origin": "unavailable",
        "timestamp_utc_origin": "source_timestamp",
        "operator_ref": "operator-fixture",
        "note": "synthetic marker",
        "label_semantics": "weak_operator_event",
        "reason_codes": ["monotonic_unavailable"],
    }
    manual_path = root / "events/manual-events.jsonl"
    _write_jsonl(manual_path, [manual_event])
    manual_artifact = _artifact(
        root,
        artifact_id="stream-manual-events",
        relative_path="events/manual-events.jsonl",
        role="stream_data",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=field_session.MANUAL_EVENT_CONTRACT_VERSION,
        privacy_class="structured_sensor",
        record_count=1,
    )
    artifacts.append(manual_artifact)
    _set_stream(
        manifest,
        stream_id="manual-event-primary",
        source="manual_event",
        artifact=manual_artifact,
        contract=field_session.MANUAL_EVENT_CONTRACT_VERSION,
        bounds=field_session._observed_bounds([manual_event]),
        variant="manual_event",
        clock_domain_id=None,
    )

    consent_path = root / "privacy/consent.json"
    retention_path = root / "privacy/retention-policy.json"
    _write_json(consent_path, {"fixture": True, "consent": "allowed"})
    _write_json(retention_path, {"fixture": True, "retention": "approved"})
    consent_artifact = _artifact(
        root,
        artifact_id="consent-evidence",
        relative_path="privacy/consent.json",
        role="consent",
        format_name="json",
        media_type="application/json",
        contract="egolink.consent.fixture.v0.1",
        privacy_class="policy_metadata",
        record_count=None,
    )
    retention_artifact = _artifact(
        root,
        artifact_id="retention-policy",
        relative_path="privacy/retention-policy.json",
        role="retention_policy",
        format_name="json",
        media_type="application/json",
        contract="egolink.retention.fixture.v0.1",
        privacy_class="policy_metadata",
        record_count=None,
    )
    artifacts.extend([consent_artifact, retention_artifact])
    manifest["privacy"].update(
        {
            "consent_status": "allowed",
            "privacy_review_status": "approved",
            "location_privacy_class": "engineering_private",
            "retention_status": "approved",
            "consent_artifact_id": consent_artifact["artifact_id"],
            "retention_policy_artifact_id": retention_artifact["artifact_id"],
            "reviewed_by": "privacy-review-fixture",
            "reviewed_at_utc": "2026-08-17T00:07:00Z",
        }
    )

    mapping_path = root / "time/clock-mappings.jsonl"
    records_path = root / "time/time-records.jsonl"
    _write_jsonl(mapping_path, [mapping])
    _write_jsonl(records_path, records)
    mapping_artifact = _artifact(
        root,
        artifact_id="clock-mappings",
        relative_path="time/clock-mappings.jsonl",
        role="clock_mapping",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=time_lineage.CLOCK_MAPPING_VERSION,
        privacy_class="private_location",
        record_count=1,
    )
    records_artifact = _artifact(
        root,
        artifact_id="time-records",
        relative_path="time/time-records.jsonl",
        role="time_lineage_records",
        format_name="jsonl",
        media_type="application/x-ndjson",
        contract=time_lineage.TIME_LINEAGE_VERSION,
        privacy_class="private_location",
        record_count=len(records),
    )
    artifacts.extend([mapping_artifact, records_artifact])
    time_report = time_lineage.validate_time_lineage(
        records,
        [mapping],
        generated_at=GENERATED_AT,
    )
    if not time_report["valid"] or not time_report["field_eligible"]:
        raise AssertionError(time_report)
    report_path = root / "time/a0-002-validation-report.json"
    _write_json(report_path, time_report)
    report_artifact = _artifact(
        root,
        artifact_id="a0-002-validation-report",
        relative_path="time/a0-002-validation-report.json",
        role="time_validation_report",
        format_name="json",
        media_type="application/json",
        contract=time_lineage.REPORT_VERSION,
        privacy_class="private_location",
        record_count=None,
    )
    artifacts.append(report_artifact)
    manifest["artifacts"] = artifacts
    manifest["time_lineage"] = {
        "record_contract_version": time_lineage.TIME_LINEAGE_VERSION,
        "mapping_contract_version": time_lineage.CLOCK_MAPPING_VERSION,
        "record_artifact_ids": [records_artifact["artifact_id"]],
        "mapping_artifact_ids": [mapping_artifact["artifact_id"]],
        "validation_report_artifact_id": report_artifact["artifact_id"],
    }
    manifest["limitations"] = [
        "Synthetic contract fixture only; it is not field, model, calibration, or Gate evidence."
    ]
    return (
        field_session.seal_manifest(
            manifest,
            sealed_by="unit-test",
            sealed_at_utc="2026-08-17T00:11:00Z",
        )
        if sealed
        else manifest
    )


def _refresh_time_report(manifest: dict, root: Path) -> None:
    records = field_session.load_jsonl(root / "time/time-records.jsonl")
    mappings = field_session.load_jsonl(root / "time/clock-mappings.jsonl")
    report = time_lineage.validate_time_lineage(records, mappings, generated_at=GENERATED_AT)
    _write_json(root / "time/a0-002-validation-report.json", report)
    for artifact_id in ("time-records", "clock-mappings", "a0-002-validation-report"):
        _refresh_artifact(manifest, root, artifact_id)


class A0FieldSessionTests(unittest.TestCase):
    def test_contract_schemas_and_draft_are_fail_closed(self) -> None:
        for path in (
            field_session.MANIFEST_SCHEMA_PATH,
            field_session.MANUAL_EVENT_SCHEMA_PATH,
            field_session.IMU_FIELD_CALIBRATED_SCHEMA_PATH,
        ):
            Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as directory:
            manifest = field_session.build_draft_manifest(
                device_id="dev-1",
                operator_ref="operator-ref",
                protocol_id="A0-003-DRAFT",
                test_scenario="draft only",
                created_at_utc="2026-08-17T00:00:00Z",
                session_id="FS-20260817T000000Z-bbbbbbbbbbbb",
            )
            report = field_session.validate_field_session(
                manifest,
                session_root=Path(directory),
                generated_at=GENERATED_AT,
            )
        self.assertTrue(report["valid"])
        self.assertFalse(report["field_eligible"])
        self.assertEqual(report["training_status"], "not_evaluated")
        self.assertFalse(report["training_eligible"])
        self.assertEqual(report["gate_status"], "unverified")

    def test_real_shaped_synthetic_fixture_can_verify_contract_but_not_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            manifest_path = root / "session.json"
            _write_json(manifest_path, manifest)
            report = field_session.validate_field_session(
                manifest,
                session_root=root,
                manifest_path=manifest_path,
                generated_at=GENERATED_AT,
            )
        self.assertTrue(report["valid"], report["errors"])
        self.assertTrue(report["field_eligible"], report["field_eligibility_reasons"])
        self.assertTrue(report["artifact_integrity_verified"])
        self.assertTrue(report["package_closure_verified"])
        self.assertTrue(report["a0_002_report_binding_verified"])
        self.assertEqual(report["field_eligibility_scope"], "structural_review_only")
        self.assertFalse(report["training_eligible"])
        self.assertEqual(report["gate_status"], "unverified")

    def test_session_ids_are_unique_and_injectable_for_reproducibility(self) -> None:
        first = field_session.generate_session_id(created_at_utc="2026-08-17T00:00:00Z")
        second = field_session.generate_session_id(created_at_utc="2026-08-17T00:00:00Z")
        self.assertNotEqual(first, second)
        self.assertEqual(
            field_session.generate_session_id(
                created_at_utc="2026-08-17T00:00:00Z",
                random_suffix="abcdef123456",
            ),
            "FS-20260817T000000Z-abcdef123456",
        )

    def test_path_traversal_and_package_extra_file_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            manifest["artifacts"][0]["path"] = "../escape.json"
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
            self.assertIn("artifact_ref_unsafe", {item["code"] for item in report["errors"]})

            manifest = _build_field_bundle(root)
            (root / "undeclared.txt").write_text("extra", encoding="utf-8")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
            self.assertIn("package_extra_file", {item["code"] for item in report["errors"]})

    def test_artifact_and_manifest_tampering_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            (root / "streams/gnss.jsonl").write_text("{}\n", encoding="utf-8")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
            self.assertIn("artifact_hash_mismatch", {item["code"] for item in report["errors"]})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            manifest["scenario"]["test_scenario"] = "tampered after seal"
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
            self.assertIn("manifest_seal_mismatch", {item["code"] for item in report["errors"]})

    def test_partial_artifact_part_metadata_is_rejected_without_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root, sealed=False)
            manifest["artifacts"][0]["part_group"] = "incomplete-group"
            report = field_session.validate_field_session(
                manifest,
                session_root=root,
                generated_at=GENERATED_AT,
            )
        self.assertFalse(report["valid"])
        self.assertIn("schema_invalid", {item["code"] for item in report["errors"]})

    def test_malformed_jsonl_is_validation_failure_not_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            malformed_path = root / "streams/lte.jsonl"
            malformed_path.write_text('{"bad": NaN}\n', encoding="utf-8")
            malformed_artifact = next(
                item for item in manifest["artifacts"] if item["artifact_id"] == "stream-lte"
            )
            malformed_artifact["sha256"] = field_session.sha256_file(malformed_path)
            malformed_artifact["size_bytes"] = malformed_path.stat().st_size
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        self.assertFalse(report["valid"])
        self.assertIn("artifact_content_invalid", {item["code"] for item in report["errors"]})

    def test_training_and_split_cannot_be_self_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            manifest["privacy"]["training_allowed"] = True
            manifest["split"]["name"] = "train"
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        self.assertFalse(report["valid"])
        self.assertIn("schema_invalid", {item["code"] for item in report["errors"]})

    def test_denied_consent_and_unapproved_raw_media_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            manifest["privacy"]["consent_status"] = "denied"
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
            self.assertIn("captured_private_data_without_consent", {item["code"] for item in report["errors"]})

            media_path = root / "media/camera.jpg"
            media_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.write_bytes(b"fixture-jpeg-not-a-real-image")
            manifest["artifacts"].append(
                _artifact(
                    root,
                    artifact_id="raw-camera-media",
                    relative_path="media/camera.jpg",
                    role="raw_media",
                    format_name="jpeg",
                    media_type="image/jpeg",
                    contract=None,
                    privacy_class="private_media",
                    record_count=None,
                )
            )
            manifest["privacy"]["consent_status"] = "allowed"
            manifest["privacy"]["raw_image_allowed"] = False
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:13:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        self.assertIn("raw_media_not_allowed", {item["code"] for item in report["errors"]})

    def test_private_media_cannot_hide_under_legacy_or_binary_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root, sealed=False)
            hidden_path = root / "private/voice.bin"
            hidden_path.parent.mkdir(parents=True, exist_ok=True)
            hidden_path.write_bytes(b"not-real-audio-fixture")
            hidden = _artifact(
                root,
                artifact_id="hidden-private-media",
                relative_path="private/voice.bin",
                role="legacy_attachment",
                format_name="binary",
                media_type="audio/wav",
                contract=None,
                privacy_class="private_media",
                record_count=None,
            )
            manifest["artifacts"].append(hidden)
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("private_media_role_invalid", codes)
        self.assertIn("media_role_mismatch", codes)
        self.assertFalse(report["field_eligible"])

    def test_bundled_time_report_is_recomputed_from_exact_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            report_path = root / "time/a0-002-validation-report.json"
            bundled = field_session.load_json(report_path)
            bundled["field_eligible"] = False
            _write_json(report_path, bundled)
            _refresh_artifact(manifest, root, "a0-002-validation-report")
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        self.assertFalse(report["a0_002_report_binding_verified"])
        self.assertIn("time_report_recompute_mismatch", {item["code"] for item in report["errors"]})

    def test_time_source_and_anchor_evidence_must_be_in_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root, sealed=False)
            rows = field_session.load_jsonl(root / "time/time-records.jsonl")
            rows[0]["lineage"]["source_record_ref"] = "outside/gnss.jsonl"
            _write_jsonl(root / "time/time-records.jsonl", rows)
            _refresh_time_report(manifest, root)
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("time_lineage_source_artifact_mismatch", codes)
        self.assertIn("time_source_evidence_not_in_package", codes)

    def test_stream_bounds_and_calibrated_extent_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root, sealed=False)
            next(stream for stream in manifest["streams"] if stream["stream_id"] == "gnss-primary")["bounds"]["sequence_last"] = 2
            next(stream for stream in manifest["streams"] if stream["stream_id"] == "imu-calibrated")["bounds"]["sequence_last"] = 2
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("stream_bounds_mismatch", codes)
        self.assertIn("derived_stream_extent_mismatch", codes)

    def test_manual_event_semantics_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root, sealed=False)
            event_path = root / "events/manual-events.jsonl"
            rows = field_session.load_jsonl(event_path)
            rows[0]["event_type"] = "OTHER"
            rows[0]["note"] = None
            rows[0]["receive_timestamp_utc"] = "2026-08-17T00:00:04Z"
            rows[0]["ingest_timestamp_utc"] = "2026-08-17T00:00:03Z"
            _write_jsonl(event_path, rows)
            _refresh_artifact(manifest, root, "stream-manual-events")
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("manual_event_other_note_missing", codes)
        self.assertIn("manual_event_ingest_before_receive", codes)

    def test_receive_time_cannot_be_promoted_to_event_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root, sealed=False)
            event_path = root / "events/manual-events.jsonl"
            rows = field_session.load_jsonl(event_path)
            rows[0]["alignment_status"] = "receive_only"
            rows[0]["timestamp_utc"] = rows[0]["receive_timestamp_utc"]
            rows[0]["timestamp_utc_origin"] = "source_timestamp"
            rows[0]["timestamp_uncertainty_ns"] = None
            _write_jsonl(event_path, rows)
            _refresh_artifact(manifest, root, "stream-manual-events")
            manifest = field_session.seal_manifest(manifest, sealed_by="test", sealed_at_utc="2026-08-17T00:12:00Z")
            report = field_session.validate_field_session(manifest, session_root=root, generated_at=GENERATED_AT)
        self.assertIn("manual_event_receive_time_promoted", {item["code"] for item in report["errors"]})

    def test_cli_exit_classes_and_seal_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "session"
            root.mkdir()
            manifest = _build_field_bundle(root, sealed=False)
            manifest_path = root / "session.json"
            _write_json(manifest_path, manifest)
            sealed_output = parent / "sealed-session.json"
            with redirect_stdout(StringIO()):
                seal_exit = field_session.main(
                    [
                        "seal",
                        "--manifest",
                        str(manifest_path),
                        "--session-root",
                        str(root),
                        "--output",
                        str(sealed_output),
                        "--sealed-by",
                        "unit-test",
                        "--sealed-at-utc",
                        "2026-08-17T00:11:00Z",
                    ]
                )
            self.assertEqual(seal_exit, 0)
            self.assertEqual(field_session.load_json(sealed_output)["seal"]["status"], "sealed")

            _write_json(manifest_path, field_session.load_json(sealed_output))
            with redirect_stdout(StringIO()):
                validate_exit = field_session.main(
                    ["validate", "--manifest", str(manifest_path), "--session-root", str(root)]
                )
            self.assertEqual(validate_exit, 0)

            malformed = parent / "malformed.json"
            malformed.write_text('{"bad": NaN}', encoding="utf-8")
            with redirect_stdout(StringIO()):
                malformed_exit = field_session.main(["validate", "--manifest", str(malformed)])
            self.assertEqual(malformed_exit, 2)

    def test_cli_report_must_not_mutate_sealed_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _build_field_bundle(root)
            manifest_path = root / "session.json"
            _write_json(manifest_path, manifest)
            with redirect_stdout(StringIO()):
                exit_code = field_session.main(
                    [
                        "validate",
                        "--manifest",
                        str(manifest_path),
                        "--report",
                        str(root / "validation-report.json"),
                    ]
                )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
