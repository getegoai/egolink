from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import analyze_gnss_acceptance as analyzer


FIXED_CREATED_AT = "2026-07-03T00:00:00+00:00"
BASE_LAT = 22.543210
BASE_LON = 113.923456


def offset_coordinate(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    new_lat = lat + north_m / 111_320.0
    new_lon = lon + east_m / (111_320.0 * 0.927)
    return new_lat, new_lon


def synthetic_fixture() -> tuple[dict, dict]:
    points = [
        {
            "point_id": "open_sky_01",
            "name": "Open Sky 01",
            "point_type": "open_sky",
            "reference": {
                "lat": BASE_LAT,
                "lon": BASE_LON,
                "method": "phone_gnss_5min_average",
                "recorded_at": "2026-07-03T08:00:00+00:00",
            },
        },
        {
            "point_id": "street_canyon_01",
            "name": "Street Between Buildings 01",
            "point_type": "street_between_buildings",
            "reference": {
                "lat": BASE_LAT + 0.001,
                "lon": BASE_LON + 0.001,
                "method": "map_pick_satellite_view",
                "recorded_at": "2026-07-03T08:10:00+00:00",
            },
        },
        {
            "point_id": "tree_cover_01",
            "name": "Tree Cover 01",
            "point_type": "tree_cover",
            "reference": {
                "lat": BASE_LAT + 0.002,
                "lon": BASE_LON + 0.002,
                "method": "phone_gnss_5min_average",
                "recorded_at": "2026-07-03T08:20:00+00:00",
            },
        },
    ]

    attempts = []
    messages = []
    seq = 1
    for point_index, point in enumerate(points):
        ref = point["reference"]
        for mode in ("cold", "warm"):
            for attempt_number in range(1, 6):
                command_id = f"cmd-{point_index + 1}-{mode}-{attempt_number}"
                attempt_id = f"{point['point_id']}-{mode}-{attempt_number:02d}"
                minute = point_index * 30 + (0 if mode == "cold" else 10) + attempt_number
                started_at = f"2026-07-03T09:{minute:02d}:00+00:00"
                received_at = f"2026-07-03T09:{minute:02d}:18+00:00"
                hdop = 1.0 + point_index * 0.7 + attempt_number * 0.1
                error_m = hdop * 5.0
                lat, lon = offset_coordinate(ref["lat"], ref["lon"], error_m, 0.0)
                attempts.append(
                    {
                        "attempt_id": attempt_id,
                        "point_id": point["point_id"],
                        "mode": mode,
                        "command_id": command_id,
                        "started_at": started_at,
                        "ended_at": f"2026-07-03T09:{minute:02d}:50+00:00",
                    }
                )
                messages.append(
                    {
                        "message_type": "event",
                        "event_type": "location_report",
                        "device_id": "ego-link-r1-connectivity-001",
                        "test_run_id": "FIELD-003-20260703-unit",
                        "seq": seq,
                        "server_received_at": received_at,
                        "fw_version": "0.1.0-field003-unit",
                        "location_request_cmd_id": command_id,
                        "transport": {"type": "lte"},
                        "source_status": "observed",
                        "fix": True,
                        "gnss_state": "fix",
                        "lat": lat,
                        "lon": lon,
                        "hdop": hdop,
                        "satellites": 9 + attempt_number,
                        "gnss_attempt_ms": 18_000,
                    }
                )
                seq += 1

    manifest = {
        "test_run_id": "FIELD-003-20260703-unit",
        "board_id": "connectivity-node-001",
        "device_id": "ego-link-r1-connectivity-001",
        "firmware_version": "0.1.0-field003-unit",
        "firmware_commit_or_image": "unit-test-image",
        "connection_path": "vps_message_hub_usb_free",
        "runtime_usb_connected": False,
        "reference_points": points,
        "attempts": attempts,
    }
    export = {
        "test_run": {"id": "FIELD-003-20260703-unit"},
        "messages": messages,
        "raw_frames": [],
    }
    return export, manifest


class GnssAcceptanceAnalysisTests(unittest.TestCase):
    def test_synthetic_fixture_computes_required_metrics(self) -> None:
        export, manifest = synthetic_fixture()

        report = analyzer.evaluate_gnss_acceptance(export, manifest, created_at=FIXED_CREATED_AT)

        self.assertEqual(report["result"]["status"], "PASS")
        self.assertEqual(report["counts"]["reference_points"], 3)
        self.assertEqual(report["counts"]["attempts"], 30)
        self.assertEqual(report["counts"]["fixed_attempts"], 30)
        self.assertEqual(report["overall"]["fix_rate"], 1.0)
        self.assertEqual(report["overall"]["ttff_s"]["p50"], 18.0)
        self.assertGreater(report["overall"]["error_m"]["p95"], 5.0)
        self.assertGreater(report["overall"]["hdop_error_correlation"], 0.99)
        self.assertEqual(report["eale_p0_comparison"]["revision_assessment"], "no_revision_indicated_by_this_run")
        self.assertFalse(report["eale_p0_comparison"]["needs_revision"])
        for point in report["per_point"]:
            self.assertEqual(point["cold_attempts"], 5)
            self.assertEqual(point["warm_attempts"], 5)
            self.assertEqual(point["fix_rate"], 1.0)

    def test_incomplete_protocol_fails_with_specific_errors(self) -> None:
        export, manifest = synthetic_fixture()
        manifest["reference_points"] = manifest["reference_points"][:1]
        manifest["attempts"] = [attempt for attempt in manifest["attempts"] if attempt["point_id"] == "open_sky_01"][:5]

        report = analyzer.evaluate_gnss_acceptance(export, manifest, created_at=FIXED_CREATED_AT)

        self.assertEqual(report["result"]["status"], "FAIL")
        self.assertIn(
            "manifest missing required reference point types: street_between_buildings, tree_cover",
            report["result"]["errors"],
        )
        self.assertIn("one or more points has fewer than five cold or five warm attempts", report["result"]["errors"])

    def test_cli_writes_json_and_markdown_report(self) -> None:
        export, manifest = synthetic_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "test_run_export.json"
            manifest_path = tmp_path / "field_manifest.json"
            output_dir = tmp_path / "out"
            input_path.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = analyzer.main(
                    [
                        "--input",
                        str(input_path),
                        "--manifest",
                        str(manifest_path),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("PASS FIELD-003 GNSS acceptance", stdout.getvalue())
            report_json = json.loads((output_dir / analyzer.REPORT_JSON).read_text(encoding="utf-8"))
            report_md = (output_dir / analyzer.REPORT_MARKDOWN).read_text(encoding="utf-8")
            self.assertEqual(report_json["result"]["status"], "PASS")
            self.assertIn("FIELD-003 GNSS Acceptance Report", report_md)
            self.assertIn("EALE-P0 Fine Radius Check", report_md)


if __name__ == "__main__":
    unittest.main()
