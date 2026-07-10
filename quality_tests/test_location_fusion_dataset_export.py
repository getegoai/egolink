from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts import export_location_fusion_dataset as exporter


FIXED_CREATED_AT = "2026-06-30T12:00:00+00:00"


def raw_frame(
    frame_id: str,
    *,
    seq: int,
    frame_type: str = "event",
    derived_message_type: str = "event",
    parse_status: str = "ok",
    server_received_at: str,
    derived_message: dict | None = None,
) -> dict:
    return {
        "protocol_version": "egolink.p0.v1",
        "transport_profile": "raw-frame.p0.v1",
        "direction": "uplink",
        "device_id": "ego-link-001",
        "fw_version": "0.1.0-loc004a-cell-observation",
        "test_run_id": "loc-fusion-unit",
        "frame_id": frame_id,
        "seq": seq,
        "server_received_at": server_received_at,
        "framing": {
            "magic": "EGLK",
            "frame_version": 1,
            "frame_type": frame_type,
            "content_type": "json",
            "payload_len": 64,
            "payload_crc32": "1234ABCD",
        },
        "raw_payload": {
            "encoding": "base64",
            "byte_len": 64,
            "sha256": f"{seq:064x}"[-64:],
            "crc32": "1234ABCD",
            "data": "SECRET_RAW_PAYLOAD_MUST_NOT_APPEAR_IN_SAMPLE",
            "data_redacted": True,
        },
        "parse_result": {
            "status": parse_status,
            "parser_version": "raw-frame.p0.v1",
            "derived_message_type": derived_message_type,
            "derived_message": derived_message or {},
        },
        "retention": {"privacy_class": "engineering", "redacted": True},
    }


def kr003_like_export() -> dict:
    cmd_id = "cmd-000001"
    report = {
        "protocol_version": "egolink.p0.v1",
        "message_type": "event",
        "event_type": "location_report",
        "device_id": "ego-link-001",
        "fw_version": "0.1.0-loc004a-cell-observation",
        "test_run_id": "loc-fusion-unit",
        "seq": 11,
        "server_received_at": "2026-06-30T12:00:01Z",
        "location_request_cmd_id": cmd_id,
        "fix": False,
        "gnss_state": "no_fix",
        "gnss_query_ok": True,
        "source": "firmware",
        "source_status": "no_fix",
        "transport": {"type": "lte"},
        "lte_http": {"phase": "location_report", "http_status": 200},
        "raw_frame": {"frame_id": f"loc-{cmd_id}"},
    }
    observation = {
        "protocol_version": "egolink.p0.v1",
        "message_type": "event",
        "event_type": "location_observation",
        "device_id": "ego-link-001",
        "fw_version": "0.1.0-loc004a-cell-observation",
        "test_run_id": "loc-fusion-unit",
        "seq": 12,
        "server_received_at": "2026-06-30T12:00:02Z",
        "location_request_cmd_id": cmd_id,
        "cell": {
            "cell_rat": "LTE",
            "mcc": "460",
            "mnc": "01",
            "tac": "1001",
            "cell_id": "2002",
            "rsrp": -91,
            "rsrq": -10,
            "rssi": -65,
            "sinr": 8,
        },
        "lte": {"registration": "registered", "pdp": "active", "assigned_ip_present": True},
        "transport": {"type": "lte"},
        "lte_http": {"phase": "location_observation", "http_status": 200},
        "location_belief": {"state": "Unknown", "confidence": 0.0, "source": "rule", "reason": "gnss_no_fix"},
        "raw_frame": {"frame_id": f"obs-{cmd_id}"},
    }
    ack = {
        "protocol_version": "egolink.p0.v1",
        "message_type": "ack",
        "device_id": "ego-link-001",
        "fw_version": "0.1.0-loc004a-cell-observation",
        "test_run_id": "loc-fusion-unit",
        "seq": 13,
        "server_received_at": "2026-06-30T12:00:03Z",
        "cmd_id": cmd_id,
        "status": "ok",
        "transport": {"type": "lte"},
        "lte_http": {"phase": "command_ack", "http_status": 200},
        "command": {
            "parse_status": "raw_command_selected",
            "command_count": 1,
            "duplicate_local_execution_prevented": True,
        },
    }
    return {
        "test_run": {
            "test_run_id": "loc-fusion-unit",
            "created_at": "2026-06-30T12:00:00Z",
            "description": "synthetic location fusion export",
        },
        "messages": [report, observation],
        "commands": [
            {
                "cmd_id": cmd_id,
                "cmd": "request_location",
                "device_id": "ego-link-001",
                "test_run_id": "loc-fusion-unit",
                "status": "ok",
                "created_at": "2026-06-30T12:00:00Z",
                "updated_at": "2026-06-30T12:00:03Z",
                "ack": ack,
            }
        ],
        "raw_frames": [
            raw_frame(
                f"loc-{cmd_id}",
                seq=11,
                server_received_at="2026-06-30T12:00:01Z",
                derived_message=report,
            ),
            raw_frame(
                f"obs-{cmd_id}",
                seq=12,
                server_received_at="2026-06-30T12:00:02Z",
                derived_message=observation,
            ),
            raw_frame(
                f"ack-{cmd_id}",
                seq=13,
                frame_type="ack",
                derived_message_type="ack",
                server_received_at="2026-06-30T12:00:03Z",
                derived_message=ack,
            ),
        ],
        "observability_summary": {
            "latest_observability": {
                "transport": {"type": "lte"},
                "runtime": {"reset_reason": "power_on"},
            }
        },
    }


class LocationFusionDatasetExportTests(unittest.TestCase):
    def test_schema_exposes_dataset_lineage_quality_privacy_and_split_fields(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        schema_path = repo_root / "shared" / "contracts" / "location_fusion_sample.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["contract_version"]["const"], exporter.CONTRACT_VERSION)
        self.assertIn("failure_window", schema["properties"]["sample_type"]["enum"])

        required = set(schema["required"])
        for field in {"lineage", "features", "labels", "quality", "privacy", "split", "generator"}:
            self.assertIn(field, required)

        raw_ref_properties = schema["properties"]["lineage"]["properties"]["raw_frame_refs"]["items"]["properties"]
        for field in {
            "frame_id",
            "byte_len",
            "sha256",
            "crc32",
            "parse_status",
            "parser_version",
            "cmd_id",
            "seq",
            "fw_version",
            "server_received_at",
        }:
            self.assertIn(field, raw_ref_properties)

    def test_builds_command_window_with_raw_lineage_and_no_payload_copy(self) -> None:
        samples, manifest = exporter.build_dataset(
            kr003_like_export(),
            split_name="holdout",
            split_rule="unit_test_session_block",
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertEqual(sample["sample_type"], "failure_window")
        self.assertEqual(sample["sample_id"], "loc-fusion-unit:cmd-000001:location")
        self.assertEqual(sample["split"], {"name": "holdout", "rule": "unit_test_session_block"})
        self.assertIn("gnss_no_fix", sample["labels"]["failure_modes"])
        self.assertEqual(sample["features"]["cell"]["cell_id"], "2002")
        self.assertEqual(sample["features"]["command"]["cmd_id"], "cmd-000001")

        raw_refs = sample["lineage"]["raw_frame_refs"]
        self.assertEqual(len(raw_refs), 3)
        self.assertEqual({ref["frame_id"] for ref in raw_refs}, {"loc-cmd-000001", "obs-cmd-000001", "ack-cmd-000001"})
        self.assertTrue(all(ref["cmd_id"] == "cmd-000001" for ref in raw_refs))
        self.assertTrue(all(ref["fw_version"] == "0.1.0-loc004a-cell-observation" for ref in raw_refs))
        self.assertTrue(all(ref["byte_len"] == 64 for ref in raw_refs))
        self.assertTrue(all(ref["parse_status"] == "ok" for ref in raw_refs))
        self.assertNotIn("SECRET_RAW_PAYLOAD_MUST_NOT_APPEAR_IN_SAMPLE", json.dumps(sample, sort_keys=True))

        self.assertEqual(manifest["counts"]["samples"], 1)
        self.assertEqual(manifest["counts"]["failure_modes"]["gnss_no_fix"], 1)
        self.assertEqual(manifest["schema"]["sample_schema"], "shared/contracts/location_fusion_sample.schema.json")

    def test_private_coordinates_are_redacted_by_default_and_training_blocked(self) -> None:
        export = kr003_like_export()
        export["messages"][0]["fix"] = True
        export["messages"][0]["gnss_state"] = "fixed"
        export["messages"][0]["lat"] = 22.123456
        export["messages"][0]["lon"] = 113.123456

        samples, _manifest = exporter.build_dataset(export, created_at=FIXED_CREATED_AT)

        sample = samples[0]
        self.assertEqual(sample["sample_type"], "known_place_calibration_window")
        self.assertTrue(sample["features"]["gnss"]["lat_present"])
        self.assertTrue(sample["features"]["gnss"]["lon_present"])
        self.assertNotIn("latitude_deg", sample["features"]["gnss"])
        self.assertNotIn("longitude_deg", sample["features"]["gnss"])
        self.assertEqual(sample["privacy"]["privacy_class"], "private_location")
        self.assertFalse(sample["privacy"]["training_allowed"])
        self.assertIn("private_location_training_not_explicitly_allowed", sample["privacy"]["exclusion_reasons"])
        self.assertIn("training_not_allowed_by_privacy_policy", sample["quality"]["warnings"])

    def test_bad_raw_frame_becomes_failure_window(self) -> None:
        bad_record = raw_frame(
            "bad-frame-001",
            seq=1,
            parse_status="checksum_failed",
            server_received_at="2026-06-30T12:01:00Z",
        )
        samples, manifest = exporter.build_dataset(
            {
                "test_run": {"test_run_id": "bad-raw-unit"},
                "messages": [],
                "commands": [],
                "raw_frames": [bad_record],
            },
            created_at=FIXED_CREATED_AT,
        )

        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertEqual(sample["sample_type"], "failure_window")
        self.assertEqual(sample["labels"]["failure_modes"], ["checksum_failed", "raw_parse_failed"])
        self.assertEqual(sample["quality"]["status"], "warn")
        self.assertIn("raw_frame_parse_failure", sample["quality"]["warnings"])
        self.assertEqual(manifest["counts"]["failure_modes"]["checksum_failed"], 1)

    def test_cli_writes_jsonl_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "test_run_export.json"
            output_dir = tmp_path / "dataset"
            input_path.write_text(json.dumps(kr003_like_export()), encoding="utf-8")

            exit_code = exporter.main(
                [
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(output_dir),
                    "--split",
                    "holdout",
                    "--split-rule",
                    "unit_test_session_block",
                ]
            )

            self.assertEqual(exit_code, 0)
            samples_path = output_dir / "samples.jsonl"
            manifest_path = output_dir / "manifest.json"
            self.assertTrue(samples_path.is_file())
            self.assertTrue(manifest_path.is_file())
            rows = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines()]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(manifest["counts"]["samples"], 1)


if __name__ == "__main__":
    unittest.main()
