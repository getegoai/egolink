from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from pc_simulator import sensor_time_lineage as time_lineage


FIELD_SESSION_ID = "FIELD-A0-002-SYNTHETIC-CONTRACT-001"
SOURCE_SEMANTICS = {
    "gnss": "measurement_time",
    "lte": "modem_event_time",
    "imu": "sample_time",
    "camera": "exposure_center",
}
SOURCE_HASH_DIGIT = {"gnss": "a", "lte": "b", "imu": "c", "camera": "d"}


def fixture_mapping(
    *, evidence_scope: str = "synthetic_fixture", drift_ppm: int = 0
) -> dict:
    mapping = {
        "contract_version": time_lineage.CLOCK_MAPPING_VERSION,
        "mapping_id": "clock-map-boot7-v1",
        "device_id": "ego-link-test-001",
        "monotonic_clock_domain_id": "connectivity-boot7-uptime",
        "boot_count": 7,
        "monotonic_origin_ns": 1_000_000,
        "utc_origin": "2026-08-17T00:00:00Z",
        "utc_rate_correction_ppm": drift_ppm,
        "valid_from_monotonic_ns": 1_000_000,
        "valid_through_monotonic_ns": 1_000_000_000,
        "anchor_method": "synthetic_two_point_fixture",
        "anchors": [],
        "anchor_count": 2,
        "fit_rms_error_ns": 0,
        "fit_max_error_ns": 0,
        "uncertainty_ns": 5000,
        "status": "verified",
        "created_at": "2026-08-17T00:01:00Z",
        "lineage": {
            "evidence_scope": evidence_scope,
            "source_status": "observed" if evidence_scope == "field_session" else "verified",
            "field_session_id": FIELD_SESSION_ID if evidence_scope == "field_session" else None,
            "firmware_commit": "1" * 40,
        },
    }
    for index, monotonic_ns in enumerate((1_000_000, 1_000_000_000), start=1):
        mapping["anchors"].append(
            {
                "anchor_id": f"map-anchor-{index}",
                "source": "host_clock",
                "timestamp_monotonic_ns": monotonic_ns,
                "timestamp_utc": time_lineage.format_utc_ns(
                    time_lineage.apply_clock_mapping(mapping, monotonic_ns)
                ),
                "uncertainty_ns": 5000,
                "source_record_ref": f"fixture://mapping/anchor/{index}",
                "source_record_sha256": ("a" if index == 1 else "b") * 64,
            }
        )
    return mapping


def fixture_record(
    source: str = "imu",
    *,
    sequence_id: int = 1,
    source_value_us: int = 1250,
    evidence_scope: str = "synthetic_fixture",
    anchor_id: str | None = "sync-anchor-1",
    mapping: dict | None = None,
) -> dict:
    mapping = mapping or fixture_mapping(evidence_scope=evidence_scope)
    monotonic_ns = source_value_us * 1000
    utc_ns = time_lineage.apply_clock_mapping(mapping, monotonic_ns)
    derivation = None
    if source == "imu":
        derivation = {
            "method": "capture_start_uptime_us_plus_offset_us",
            "window_id": "imuw-fixture-b7",
            "capture_start_uptime_us": 1000,
            "capture_end_uptime_us": 10_000,
            "offset_us": source_value_us - 1000,
        }
    return {
        "contract_version": time_lineage.TIME_LINEAGE_VERSION,
        "observation_id": f"obs-{source}-{sequence_id}-b7",
        "device_id": mapping["device_id"],
        "source": source,
        "stream_id": f"{source}-stream",
        "sequence_id": sequence_id,
        "monotonic_clock_domain_id": mapping["monotonic_clock_domain_id"],
        "boot_count": mapping["boot_count"],
        "timestamp_monotonic_ns": monotonic_ns,
        "timestamp_utc": time_lineage.format_utc_ns(utc_ns),
        "source_timestamp": {
            "raw_value": source_value_us,
            "unit": "us",
            "clock_domain_id": mapping["monotonic_clock_domain_id"],
            "semantics": SOURCE_SEMANTICS[source],
            "source_field": "fixture.source_uptime_us",
        },
        "receive_timestamp_utc": "2026-08-17T00:00:01Z",
        "ingest_timestamp_utc": "2026-08-17T00:00:02Z",
        "alignment": {
            "status": "verified",
            "timestamp_monotonic_origin": "source_timestamp",
            "monotonic_source_field": "fixture.source_uptime_us",
            "timestamp_utc_origin": "clock_mapping",
            "mapping_id": mapping["mapping_id"],
            "anchor": (
                {
                    "anchor_id": anchor_id,
                    "method": "synthetic_simultaneous_event",
                    "evidence_ref": f"fixture://sync/{anchor_id}",
                    "evidence_sha256": "e" * 64,
                }
                if anchor_id is not None
                else None
            ),
            "uncertainty_ns": mapping["uncertainty_ns"],
            "reason_codes": [],
        },
        "lineage": {
            "evidence_scope": evidence_scope,
            "source_status": "observed" if evidence_scope == "field_session" else "verified",
            "field_session_id": FIELD_SESSION_ID if evidence_scope == "field_session" else None,
            "test_run_id": "A0-002-SYNTHETIC-001",
            "firmware_version": "synthetic-test-only",
            "firmware_commit": "1" * 40,
            "source_record_ref": f"fixture://{source}/{sequence_id}",
            "source_record_sha256": SOURCE_HASH_DIGIT[source] * 64,
        },
        "imu_sample_derivation": derivation,
    }


def receive_only_lte() -> dict:
    record = fixture_record("lte")
    record.update(
        {
            "monotonic_clock_domain_id": None,
            "boot_count": None,
            "timestamp_monotonic_ns": None,
            "timestamp_utc": None,
            "source_timestamp": {
                "raw_value": None,
                "unit": "unavailable",
                "clock_domain_id": None,
                "semantics": "unknown",
                "source_field": None,
            },
            "alignment": {
                "status": "receive_only",
                "timestamp_monotonic_origin": "unavailable",
                "monotonic_source_field": None,
                "timestamp_utc_origin": "unavailable",
                "mapping_id": None,
                "anchor": None,
                "uncertainty_ns": None,
                "reason_codes": ["lte_device_monotonic_missing", "source_timestamp_unavailable"],
            },
        }
    )
    return record


class A0UnifiedTimestampTests(unittest.TestCase):
    def test_contract_schemas_and_one_mapped_record_are_valid(self) -> None:
        for path in (
            time_lineage.TIME_LINEAGE_SCHEMA_PATH,
            time_lineage.CLOCK_MAPPING_SCHEMA_PATH,
        ):
            Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
        mapping = fixture_mapping()
        report = time_lineage.validate_time_lineage(
            [fixture_record(mapping=mapping)],
            [mapping],
            required_sources=("imu",),
            generated_at="2026-08-17T00:02:00Z",
        )
        self.assertTrue(report["valid"])
        self.assertFalse(report["field_eligible"])
        self.assertEqual(report["gate_status"], "unverified")

    def test_legacy_timestamp_classification_never_invents_an_anchor(self) -> None:
        uptime = time_lineage.classify_legacy_timestamp("uptime_ms:12345")
        self.assertEqual(uptime["timestamp_monotonic_ns"], 12_345_000_000)
        self.assertIsNone(uptime["timestamp_utc"])
        ambiguous_utc = time_lineage.classify_legacy_timestamp("2026-08-17T00:00:00Z")
        self.assertEqual(ambiguous_utc["kind"], "ambiguous_iso_utc")
        self.assertIsNone(ambiguous_utc["timestamp_utc"])
        self.assertEqual(ambiguous_utc["legacy_utc_candidate"], "2026-08-17T00:00:00Z")
        self.assertEqual(
            time_lineage.classify_legacy_timestamp("raw_frame:rf-1")["kind"],
            "opaque_placeholder",
        )
        self.assertEqual(
            time_lineage.classify_legacy_timestamp("2026-08-17T08:00:00")["kind"],
            "unrecognized",
        )

    def test_utc_requires_an_explicit_zero_offset(self) -> None:
        for invalid in ("2026-08-17T08:00:00", "2026-08-17T08:00:00+08:00"):
            with self.assertRaises(time_lineage.SensorTimeLineageError):
                time_lineage.parse_utc_ns(invalid)
        expected = time_lineage.parse_utc_ns("2026-08-17T00:00:00.123456789Z")
        self.assertEqual(time_lineage.format_utc_ns(expected), "2026-08-17T00:00:00.123456789Z")

    def test_receive_only_lte_is_valid_but_never_field_eligible(self) -> None:
        report = time_lineage.validate_time_lineage(
            [receive_only_lte()],
            required_sources=("lte",),
            generated_at="2026-08-17T00:02:00Z",
        )
        self.assertTrue(report["valid"])
        self.assertFalse(report["field_eligible"])
        self.assertIn("verified_field_lineage_missing:lte", report["field_eligibility_reasons"])

    def test_receive_time_cannot_be_promoted_to_source_time(self) -> None:
        record = receive_only_lte()
        record["timestamp_utc"] = record["receive_timestamp_utc"]
        record["alignment"]["timestamp_utc_origin"] = "source_timestamp"
        report = time_lineage.validate_time_lineage(
            [record], required_sources=("lte",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("direct_source_utc_unparseable", codes)
        self.assertIn("receive_time_promoted", codes)

    def test_ingest_time_cannot_precede_receive_time(self) -> None:
        record = receive_only_lte()
        record["receive_timestamp_utc"] = "2026-08-17T00:00:03Z"
        record["ingest_timestamp_utc"] = "2026-08-17T00:00:02Z"
        report = time_lineage.validate_time_lineage(
            [record], required_sources=("lte",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        self.assertIn("ingest_before_receive", {item["code"] for item in report["errors"]})

    def test_imu_sample_time_is_start_plus_offset_in_nanoseconds(self) -> None:
        self.assertEqual(
            time_lineage.derive_imu_sample_monotonic_ns(1000, 250, 2000),
            1_250_000,
        )
        mapping = fixture_mapping()
        record = fixture_record(mapping=mapping)
        record["timestamp_monotonic_ns"] += 1
        report = time_lineage.validate_time_lineage(
            [record], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("monotonic_source_mismatch", codes)
        self.assertIn("imu_monotonic_mismatch", codes)

    def test_clock_mapping_is_bounded_and_cannot_upgrade_estimated_to_verified(self) -> None:
        mapping = fixture_mapping()
        with self.assertRaises(time_lineage.SensorTimeLineageError):
            time_lineage.apply_clock_mapping(mapping, 999_999)
        mapping["status"] = "estimated"
        record = fixture_record(mapping=mapping)
        report = time_lineage.validate_time_lineage(
            [record], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertIn(
            "estimated_mapping_claimed_verified",
            {item["code"] for item in report["errors"]},
        )

    def test_nonzero_drift_changes_only_utc_not_imu_monotonic_time(self) -> None:
        mapping = fixture_mapping(drift_ppm=100)
        record = fixture_record(source_value_us=1250, mapping=mapping)
        report = time_lineage.validate_time_lineage(
            [record], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertTrue(report["valid"])
        self.assertEqual(record["timestamp_monotonic_ns"], 1_250_000)
        self.assertEqual(record["timestamp_utc"], "2026-08-17T00:00:00.000250025Z")

    def test_direct_utc_and_free_form_anchor_cannot_claim_verified_field_alignment(self) -> None:
        field_mapping = fixture_mapping(evidence_scope="field_session")
        records = []
        for index, source in enumerate(time_lineage.SOURCES):
            record = fixture_record(
                source,
                source_value_us=1000 + index,
                evidence_scope="field_session",
                anchor_id="unbound-anchor",
                mapping=field_mapping,
            )
            record["source_timestamp"] = {
                "raw_value": record["timestamp_utc"],
                "unit": "iso8601",
                "clock_domain_id": f"{source}-source-utc",
                "semantics": "message_time",
                "source_field": f"fixture.{source}.utc",
            }
            record["alignment"].update(
                {
                    "timestamp_monotonic_origin": "device_capture",
                    "monotonic_source_field": f"fixture.{source}.device_capture_ns",
                    "timestamp_utc_origin": "source_timestamp",
                    "mapping_id": None,
                }
            )
            record["imu_sample_derivation"] = None
            records.append(record)
        report = time_lineage.validate_time_lineage(
            records, generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        self.assertFalse(report["field_eligible"])
        self.assertIn("aligned_clock_mapping_required", {item["code"] for item in report["errors"]})
        self.assertEqual(report["alignment"]["status"], "unavailable")

    def test_sequence_reset_requires_a_new_boot_scope(self) -> None:
        mapping = fixture_mapping()
        first = fixture_record(sequence_id=2, source_value_us=1250, mapping=mapping)
        second = fixture_record(sequence_id=1, source_value_us=1350, mapping=mapping)
        report = time_lineage.validate_time_lineage(
            [first, second], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertIn("sequence_not_increasing", {item["code"] for item in report["errors"]})

        second = copy.deepcopy(second)
        second["observation_id"] = "obs-imu-1-b8"
        second["boot_count"] = 8
        second["monotonic_clock_domain_id"] = "connectivity-boot8-uptime"
        second["source_timestamp"]["clock_domain_id"] = second["monotonic_clock_domain_id"]
        second["alignment"] = {
            "status": "unavailable",
            "timestamp_monotonic_origin": "source_timestamp",
            "monotonic_source_field": "fixture.source_uptime_us",
            "timestamp_utc_origin": "unavailable",
            "mapping_id": None,
            "anchor": None,
            "uncertainty_ns": None,
            "reason_codes": ["utc_anchor_missing"],
        }
        second["timestamp_utc"] = None
        report = time_lineage.validate_time_lineage(
            [first, second], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertNotIn("sequence_not_increasing", {item["code"] for item in report["errors"]})

    def test_missing_middle_timestamp_does_not_hide_later_regression(self) -> None:
        mapping = fixture_mapping()
        first = fixture_record(sequence_id=1, source_value_us=2000, mapping=mapping)
        middle = fixture_record(sequence_id=2, source_value_us=3000, mapping=mapping)
        middle["timestamp_monotonic_ns"] = None
        middle["timestamp_utc"] = None
        last = fixture_record(sequence_id=3, source_value_us=1500, mapping=mapping)
        report = time_lineage.validate_time_lineage(
            [first, middle, last],
            [mapping],
            required_sources=("imu",),
            generated_at="2026-08-17T00:02:00Z",
        )
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("monotonic_not_increasing", codes)
        self.assertIn("utc_time_regression", codes)

    def test_duplicate_observation_is_idempotent_but_conflict_fails(self) -> None:
        mapping = fixture_mapping()
        record = fixture_record(mapping=mapping)
        report = time_lineage.validate_time_lineage(
            [record, copy.deepcopy(record)],
            [mapping],
            required_sources=("imu",),
            generated_at="2026-08-17T00:02:00Z",
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["input"]["unique_record_count"], 1)
        self.assertEqual(report["input"]["idempotent_duplicate_count"], 1)

        conflict = copy.deepcopy(record)
        conflict["receive_timestamp_utc"] = "2026-08-17T00:00:03Z"
        report = time_lineage.validate_time_lineage(
            [record, conflict], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertIn("observation_id_conflict", {item["code"] for item in report["errors"]})

    def test_no_common_verified_anchor_means_sync_error_unavailable(self) -> None:
        mapping = fixture_mapping(evidence_scope="field_session")
        records = [
            fixture_record(
                source,
                source_value_us=1000 + (index * 1000),
                sequence_id=1,
                evidence_scope="field_session",
                anchor_id=f"anchor-{source}",
                mapping=mapping,
            )
            for index, source in enumerate(time_lineage.SOURCES)
        ]
        report = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["alignment"]["status"], "unavailable")
        self.assertIsNone(report["alignment"]["max_observed_anchor_span_ns"])
        self.assertIsNone(report["alignment"]["max_conservative_alignment_bound_ns"])
        self.assertFalse(report["field_eligible"])

    def test_common_four_source_field_anchor_reports_metric_without_passing_gate(self) -> None:
        mapping = fixture_mapping(evidence_scope="field_session")
        records = [
            fixture_record(
                source,
                source_value_us=1000 + (index * 1000),
                sequence_id=1,
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            )
            for index, source in enumerate(time_lineage.SOURCES)
        ]
        report = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertTrue(report["valid"])
        self.assertTrue(report["field_eligible"])
        self.assertEqual(report["alignment"]["max_observed_anchor_span_ns"], 3_000_000)
        self.assertEqual(
            report["alignment"]["max_conservative_alignment_bound_ns"],
            3_010_000,
        )
        self.assertEqual(report["gate_status"], "unverified")

    def test_common_anchor_span_uses_all_rows_instead_of_last_row_per_source(self) -> None:
        mapping = fixture_mapping(evidence_scope="field_session")
        records = [
            fixture_record(
                "gnss",
                sequence_id=1,
                source_value_us=1000,
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            ),
            fixture_record(
                "gnss",
                sequence_id=2,
                source_value_us=11_000,
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            ),
        ]
        records.extend(
            fixture_record(
                source,
                source_value_us=1000 + index * 1000,
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            )
            for index, source in enumerate(("lte", "imu", "camera"), start=1)
        )
        report = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertTrue(report["valid"])
        self.assertTrue(report["field_eligible"])
        self.assertEqual(report["alignment"]["max_observed_anchor_span_ns"], 10_000_000)
        self.assertEqual(
            report["alignment"]["max_conservative_alignment_bound_ns"],
            10_010_000,
        )

    def test_field_record_cannot_use_a_synthetic_mapping(self) -> None:
        mapping = fixture_mapping(evidence_scope="synthetic_fixture")
        records = [
            fixture_record(
                source,
                source_value_us=1000 + index,
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            )
            for index, source in enumerate(time_lineage.SOURCES)
        ]
        report = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        self.assertFalse(report["field_eligible"])
        self.assertIn("field_mapping_lineage_mismatch", {item["code"] for item in report["errors"]})

    def test_semantic_errors_are_reported_without_crashing_alignment_analysis(self) -> None:
        mapping = fixture_mapping(evidence_scope="field_session")
        records = [
            fixture_record(
                source,
                source_value_us=1000 + index,
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            )
            for index, source in enumerate(time_lineage.SOURCES)
        ]
        records[0]["alignment"]["uncertainty_ns"] = None
        report = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        self.assertFalse(report["field_eligible"])
        self.assertIn("alignment_uncertainty_missing", {item["code"] for item in report["errors"]})

        records[0] = fixture_record(
            "gnss",
            source_value_us=1000,
            evidence_scope="field_session",
            anchor_id="shared-anchor",
            mapping=mapping,
        )
        records[0]["timestamp_utc"] = "2026-08-17T00:00:00.1234567890Z"
        report = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        self.assertFalse(report["field_eligible"])

    def test_oversized_integer_is_rejected_as_schema_data(self) -> None:
        mapping = fixture_mapping()
        record = fixture_record(mapping=mapping)
        record["sequence_id"] = time_lineage.MAX_INT64 + 1
        report = time_lineage.validate_time_lineage(
            [record], [mapping], required_sources=("imu",), generated_at="2026-08-17T00:02:00Z"
        )
        self.assertFalse(report["valid"])
        self.assertIn("schema_invalid", {item["code"] for item in report["errors"]})

    def test_missing_camera_or_receive_only_lte_blocks_field_eligibility(self) -> None:
        mapping = fixture_mapping(evidence_scope="field_session")
        records = [
            fixture_record(
                source,
                source_value_us=1000 + (index * 1000),
                evidence_scope="field_session",
                anchor_id="shared-anchor",
                mapping=mapping,
            )
            for index, source in enumerate(("gnss", "lte", "imu"))
        ]
        missing_camera = time_lineage.validate_time_lineage(
            records, [mapping], generated_at="2026-08-17T00:02:00Z"
        )
        self.assertIn("required_source_missing:camera", missing_camera["field_eligibility_reasons"])

        records[1] = receive_only_lte()
        receive_only = time_lineage.validate_time_lineage(
            records
            + [
                fixture_record(
                    "camera",
                    source_value_us=4000,
                    evidence_scope="field_session",
                    anchor_id="shared-anchor",
                    mapping=mapping,
                )
            ],
            [mapping],
            generated_at="2026-08-17T00:02:00Z",
        )
        self.assertFalse(receive_only["field_eligible"])
        self.assertIn("verified_field_lineage_missing:lte", receive_only["field_eligibility_reasons"])

    def test_verified_mapping_requires_two_anchors_hashes_and_honest_uncertainty(self) -> None:
        mapping = fixture_mapping()
        mapping["anchors"] = mapping["anchors"][:1]
        mapping["anchor_count"] = 1
        mapping["uncertainty_ns"] = 1000
        report = time_lineage.validate_time_lineage(
            [], [mapping], required_sources=(), generated_at="2026-08-17T00:02:00Z"
        )
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("verified_mapping_needs_two_anchors", codes)
        self.assertIn("mapping_uncertainty_too_small", codes)

    def test_cli_uses_0_for_valid_contract_1_for_validation_and_2_for_input(self) -> None:
        mapping = fixture_mapping()
        record = fixture_record(mapping=mapping)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            mappings_path = root / "mappings.jsonl"
            records_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            mappings_path.write_text(json.dumps(mapping) + "\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(
                    time_lineage.main(
                        [
                            str(records_path),
                            "--mappings",
                            str(mappings_path),
                            "--required-sources",
                            "imu",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    time_lineage.main(
                        [
                            str(records_path),
                            "--mappings",
                            str(mappings_path),
                            "--required-sources",
                            "imu",
                            "--fail-if-ineligible",
                        ]
                    ),
                    1,
                )
            record["timestamp_monotonic_ns"] += 1
            records_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(
                    time_lineage.main([str(records_path), "--mappings", str(mappings_path)]),
                    1,
                )
            records_path.write_text("{not-json}\n", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(time_lineage.main([str(records_path)]), 2)
            records_path.write_text('{"value": NaN}\n', encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(time_lineage.main([str(records_path)]), 2)


if __name__ == "__main__":
    unittest.main()
