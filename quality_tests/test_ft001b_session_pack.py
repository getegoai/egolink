from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pc_simulator import field_session, field_session_replay
from quality_tests.test_field_session_pack import (
    FIRMWARE_COMMIT,
    FIRMWARE_IMAGE_SHA256,
    REPOSITORY_COMMIT,
    _fixture,
    _write_json,
)
from tools import pack_ft001b_session as packer


SESSION_ID = "FS-20260818T000000Z-a1b2c3d4e5f6"


def _without_lte(paths: dict) -> None:
    field_export = paths["field_value"]
    field_export["messages"] = [
        row
        for row in field_export["messages"]
        if row.get("event_type") != "location_observation"
    ]
    field_export["window"]["returned"]["messages"] = len(field_export["messages"])
    _write_json(paths["field"], field_export)


def _pack(paths: dict, output_name: str = "ft001b") -> dict:
    return packer.pack_ft001b(
        field_export_path=paths["field"],
        imu_windows_path=paths["imu"],
        calibration_artifact_path=paths["calibration"],
        output_dir=paths["field"].parent / output_name,
        test_scenario="asynchronous GNSS and IMU fixture",
        firmware_commit=FIRMWARE_COMMIT,
        firmware_image_sha256=FIRMWARE_IMAGE_SHA256,
        repository_commit=REPOSITORY_COMMIT,
        session_id=SESSION_ID,
    )


class FT001BSessionPackTests(unittest.TestCase):
    def test_minimum_gnss_imu_package_is_valid_without_lte_or_camera(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            _without_lte(paths)
            result = _pack(paths)
            manifest_path = root / "ft001b/manifest.json"
            manifest = field_session.load_json(manifest_path)
            validation = field_session.validate_field_session(
                manifest,
                session_root=manifest_path.parent,
                manifest_path=manifest_path,
            )
            package = field_session_replay.load_replay_package(manifest_path)
            replay = field_session_replay.write_replay_outputs(package, root / "replay-output")

        self.assertTrue(result["ok"])
        self.assertEqual(result["gate_status"], "unverified")
        self.assertFalse(result["field_eligible"])
        self.assertEqual(result["source_counts"]["lte"], 0)
        self.assertEqual(result["source_counts"]["gnss_valid_fix_with_coordinate"], 2)
        self.assertEqual(result["honesty"]["continuous_imu_120s"], "not_evaluated_by_packer")
        self.assertEqual(result["honesty"]["imu_coverage"]["window_count"], 1)
        self.assertGreater(result["honesty"]["imu_coverage"]["capture_interval_duration_s"], 0)
        self.assertEqual(manifest["capture_profile"]["required_sources"], ["gnss", "imu"])
        self.assertIn("lte", manifest["capture_profile"]["optional_sources"])
        self.assertIn("camera", manifest["capture_profile"]["optional_sources"])
        lte_stream = next(row for row in manifest["streams"] if row["source"] == "lte")
        camera_stream = next(row for row in manifest["streams"] if row["source"] == "camera")
        self.assertEqual(lte_stream["status"], "declared_unavailable")
        self.assertEqual(camera_stream["status"], "not_requested")
        self.assertEqual(manifest["capture_interval"]["start_utc"], "2026-08-17T00:00:10Z")
        self.assertNotEqual(manifest["capture_interval"]["start_utc"], "2026-08-17T00:00:00Z")
        self.assertNotEqual(manifest["capture_interval"]["end_utc"], "2026-08-17T00:02:00Z")
        self.assertTrue(validation["valid"])
        self.assertFalse(validation["field_eligible"])
        self.assertEqual(replay["gate_status"], "unverified")
        self.assertGreater(replay["execution"]["timeline"]["record_count"], 0)

    def test_capture_time_is_preserved_and_receive_time_stays_transport_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            result = _pack(paths)
            rows = field_session.load_jsonl(root / "ft001b/time/time-records.jsonl")

        gnss = next(row for row in rows if row["observation_id"] == "gnss-10")
        self.assertEqual(result["source_counts"]["lte"], 1)
        self.assertEqual(gnss["timestamp_utc"], "2026-08-17T00:00:10Z")
        self.assertEqual(gnss["receive_timestamp_utc"], "2026-08-17T00:00:20Z")
        self.assertIsNone(gnss["ingest_timestamp_utc"])
        self.assertEqual(gnss["alignment"]["timestamp_utc_origin"], "source_timestamp")
        self.assertEqual(gnss["alignment"]["status"], "unavailable")
        self.assertIsNone(gnss["timestamp_monotonic_ns"])

    def test_same_boot_gnss_uptime_builds_an_explicit_estimated_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            second_gnss = next(
                row
                for row in paths["field_value"]["messages"]
                if row.get("event_type") == "location_report" and row["seq"] == 12
            )
            second_gnss["ts"] = "uptime_ms:12000"
            boot_count = paths["imu_value"][0]["boot_count"]
            for row in paths["field_value"]["messages"]:
                if row.get("event_type") == "location_report":
                    row["boot_count"] = boot_count
            _write_json(paths["field"], paths["field_value"])
            result = _pack(paths)
            rows = field_session.load_jsonl(root / "ft001b/time/time-records.jsonl")
            mappings = field_session.load_jsonl(root / "ft001b/time/clock-mappings.jsonl")

        self.assertEqual(result["time_status"]["gnss"], "see_manifest_time_lineage")
        gnss_rows = [row for row in rows if row["source"] == "gnss"]
        self.assertEqual(len(gnss_rows), 2)
        self.assertTrue(all(row["alignment"]["status"] == "estimated" for row in gnss_rows))
        self.assertEqual(
            [row["timestamp_monotonic_ns"] for row in gnss_rows],
            [10_000_000_000, 12_000_000_000],
        )
        self.assertTrue(
            any(row["mapping_id"] == "map-gnss-source-estimated" for row in mappings)
        )

    def test_gnss_uptime_without_per_observation_boot_scope_stays_unaligned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            second_gnss = next(
                row
                for row in paths["field_value"]["messages"]
                if row.get("event_type") == "location_report" and row["seq"] == 12
            )
            second_gnss["ts"] = "uptime_ms:12000"
            _write_json(paths["field"], paths["field_value"])
            _pack(paths)
            rows = field_session.load_jsonl(root / "ft001b/time/time-records.jsonl")

        gnss_rows = [row for row in rows if row["source"] == "gnss"]
        self.assertTrue(all(row["alignment"]["status"] == "unavailable" for row in gnss_rows))
        self.assertTrue(all(row["boot_count"] is None for row in gnss_rows))
        self.assertTrue(all(row["timestamp_monotonic_ns"] is None for row in gnss_rows))

    def test_boot_scoped_gnss_uptime_survives_when_source_utc_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            boot_count = paths["imu_value"][0]["boot_count"]
            uptime_ms = 10_000
            for row in paths["field_value"]["messages"]:
                if row.get("event_type") == "location_report":
                    row["boot_count"] = boot_count
                    row["ts"] = f"uptime_ms:{uptime_ms}"
                    row.pop("utc_date", None)
                    row.pop("utc_time", None)
                    uptime_ms += 2_000
            _write_json(paths["field"], paths["field_value"])
            _pack(paths)
            rows = field_session.load_jsonl(root / "ft001b/time/time-records.jsonl")

        gnss_rows = [row for row in rows if row["source"] == "gnss"]
        self.assertEqual([row["boot_count"] for row in gnss_rows], [boot_count, boot_count])
        self.assertEqual(
            [row["timestamp_monotonic_ns"] for row in gnss_rows],
            [10_000_000_000, 12_000_000_000],
        )
        self.assertTrue(all(row["timestamp_utc"] is None for row in gnss_rows))
        self.assertTrue(all(row["alignment"]["status"] == "unavailable" for row in gnss_rows))

    def test_location_rows_and_scenario_claims_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            location = next(
                row for row in paths["field_value"]["messages"]
                if row.get("event_type") == "location_report"
            )
            location["message_type"] = "status"
            _write_json(paths["field"], paths["field_value"])
            with self.assertRaisesRegex(packer.FT001BPackError, "unknown message_type"):
                _pack(paths, "wrong-type")

            paths = _fixture(root)
            location = next(
                row for row in paths["field_value"]["messages"]
                if row.get("event_type") == "location_report"
            )
            location.pop("lat")
            _write_json(paths["field"], paths["field_value"])
            with self.assertRaisesRegex(packer.FT001BPackError, "requires valid coordinates"):
                _pack(paths, "missing-coordinate")

            paths = _fixture(root)
            result = _pack(paths, "honest-scenario")
            manifest = field_session.load_json(root / "honest-scenario/manifest.json")

        self.assertEqual(manifest["scenario"]["declared_carry_conditions"], [])
        self.assertEqual(manifest["scenario"]["declared_motion_conditions"], [])
        self.assertEqual(manifest["scenario"]["declared_environments"], [])
        self.assertEqual(
            result["honesty"]["gnss_trajectory"],
            "candidate_for_replay_not_quality_accepted",
        )

    def test_source_status_is_not_promoted_to_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            gnss = next(
                row for row in paths["field_value"]["messages"]
                if row.get("event_type") == "location_report"
            )
            gnss["source_status"] = "synthetic"
            _write_json(paths["field"], paths["field_value"])
            with self.assertRaisesRegex(packer.FT001BPackError, "source_status"):
                _pack(paths, "synthetic")

            paths = _fixture(root)
            _pack(paths, "lte-unknown")
            rows = field_session.load_jsonl(root / "lte-unknown/time/time-records.jsonl")

        lte = next(row for row in rows if row["source"] == "lte")
        self.assertEqual(lte["lineage"]["source_status"], "unknown")

    def test_invalid_export_shape_fails_before_writing_a_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            paths["field_value"]["commands"] = {}
            _write_json(paths["field"], paths["field_value"])
            with self.assertRaisesRegex(packer.FT001BPackError, "must all be arrays"):
                _pack(paths)
            self.assertFalse((root / "ft001b").exists())

    def test_cli_runs_the_actual_entrypoint_and_reports_unverified_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            _without_lte(paths)
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/pack_ft001b_session.py",
                    "--field-export",
                    str(paths["field"]),
                    "--imu-windows",
                    str(paths["imu"]),
                    "--calibration-artifact",
                    str(paths["calibration"]),
                    "--output-dir",
                    str(root / "cli-output"),
                    "--test-scenario",
                    "fixture",
                    "--firmware-commit",
                    FIRMWARE_COMMIT,
                    "--firmware-image-sha256",
                    FIRMWARE_IMAGE_SHA256,
                    "--repository-commit",
                    REPOSITORY_COMMIT,
                    "--session-id",
                    SESSION_ID,
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence_scope"], "engineering_smoke_only")
        self.assertEqual(result["gate_status"], "unverified")


if __name__ == "__main__":
    unittest.main()
