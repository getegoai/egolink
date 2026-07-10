from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from quality_tests.test_gnss_acceptance_analysis import BASE_LAT, BASE_LON
from scripts import summarize_location_field_evidence as field
from scripts import summarize_location_data_flywheel as flywheel
from server import message_hub


DEVICE_ID = "ego-link-r1-connectivity-001"


def sample(
    idx: int,
    *,
    collected_at: str,
    seq: int,
    cell_id: str,
    gnss_state: str,
    gnss_fix: bool | None,
    battery_mv: int,
    soc_pct: float,
    coordinate_seen: bool = True,
) -> dict[str, object]:
    return {
        "collected_at": collected_at,
        "ok": True,
        "device_id": DEVICE_ID,
        "d1_status": "estimate_visible",
        "d1_gate_status": "ready",
        "location_state": "Predicted",
        "last_device_upload_at": collected_at,
        "last_location_upload_at": collected_at,
        "freshness_s": 3.0,
        "last_seq": seq,
        "map_mode": "coordinate" if gnss_state == "fix" else "memory_coordinate",
        "lat": BASE_LAT + (idx * 0.000001),
        "lon": BASE_LON + (idx * 0.000001),
        "coordinate_seen": coordinate_seen,
        "track_point_count": 10 + idx,
        "coordinate_event_count": 20 + idx,
        "raw_post_attempt_count": 30 + idx,
        "raw_post_success_count": 30 + idx,
        "raw_post_failure_count": 0,
        "raw_post_success_rate": 1.0,
        "location_event_count": 40 + idx,
        "power_sample_count": 4 + idx,
        "battery_mv": battery_mv,
        "soc_pct": soc_pct,
        "power_evidence_status": "measured",
        "gnss_seen": True,
        "gnss_fix": gnss_fix,
        "gnss_state": gnss_state,
        "gnss_reason_code": "FIX" if gnss_state == "fix" else "GNSS_NO_FIX",
        "cell_lte_seen": True,
        "cell_rat": "LTE",
        "cell_id": cell_id,
        "cell_registration_state": "registered_home",
        "cell_pdp_state": "active",
        "imu_seen": True,
        "imu_evidence_status": "mock",
    }


def write_field_fixture(root: Path) -> tuple[Path, Path]:
    run_dir = root / "d1_field_observation" / "FIELD-UNIT-001"
    run_dir.mkdir(parents=True)
    samples_path = run_dir / field.SAMPLES_JSONL
    samples = [
        sample(
            0,
            collected_at="2026-07-09T01:00:00+00:00",
            seq=100,
            cell_id="private-cell-alpha",
            gnss_state="unknown",
            gnss_fix=None,
            battery_mv=4200,
            soc_pct=91.0,
        ),
        sample(
            1,
            collected_at="2026-07-09T01:05:00+00:00",
            seq=110,
            cell_id="private-cell-beta",
            gnss_state="no_fix",
            gnss_fix=False,
            battery_mv=4188,
            soc_pct=90.0,
        ),
        sample(
            2,
            collected_at="2026-07-09T01:10:00+00:00",
            seq=120,
            cell_id="private-cell-beta",
            gnss_state="fix",
            gnss_fix=True,
            battery_mv=4175,
            soc_pct=89.0,
        ),
    ]
    samples_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in samples),
        encoding="utf-8",
    )
    report_path = run_dir / field.D1_OBSERVATION_REPORT_JSON
    report_path.write_text(
        json.dumps(
            {
                "tool": "observe_d1_field_run",
                "run_id": "FIELD-UNIT-001",
                "result": "PASS",
                "device_id": DEVICE_ID,
                "summary": {
                    "sample_count": 3,
                    "coordinate_sample_count": 3,
                    "raw_post_success_delta": 2,
                    "cell_ids": ["private-cell-alpha", "private-cell-beta"],
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return samples_path, report_path


class LocationFieldEvidenceTests(unittest.TestCase):
    def test_builds_bounded_field_evidence_without_private_coordinates_or_cell_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_path, _ = write_field_fixture(root)

            report = field.build_location_field_evidence(
                samples_path=samples_path,
                generated_at="2026-07-09T13:00:00+00:00",
                run_id="unit-field-evidence",
            )
            d5_bundle = field.build_field_data_flywheel(
                field_report=report,
                generated_at="2026-07-09T13:00:00+00:00",
                run_id="unit-field-evidence-data-flywheel",
            )

        summary = report["summary"]
        status = d5_bundle["data_flywheel_status"]
        packet = d5_bundle["review_packet"]
        self.assertEqual(report["schema_version"], "egolink.location_field_evidence.v0.1")
        self.assertEqual(summary["samples_total"], 3)
        self.assertEqual(summary["gnss_fix_samples"], 1)
        self.assertEqual(summary["gnss_no_fix_samples"], 1)
        self.assertEqual(summary["cell_unique_count"], 2)
        self.assertEqual(summary["raw_post_success_delta"], 2)
        self.assertEqual(status["pipeline_stage"], "field_evidence_review_packet_pending")
        self.assertEqual(status["counts"]["location_field_evidence_reports"], 1)
        self.assertEqual(status["counts"]["field_samples"], 3)
        self.assertEqual(packet["record_type_counts"]["location_field_session"], 1)
        self.assertEqual(packet["record_type_counts"]["location_gnss_fix_window"], 1)
        self.assertFalse(status["readiness"]["model_training_ready"])
        self.assertFalse(report["privacy"]["raw_coordinates_exposed"])
        payload = json.dumps({"field": report, "flywheel": d5_bundle}, ensure_ascii=False)
        self.assertNotIn(f"{BASE_LAT:.6f}", payload)
        self.assertNotIn(f"{BASE_LON:.6f}", payload)
        self.assertNotIn("private-cell-alpha", payload)
        self.assertNotIn("private-cell-beta", payload)
        self.assertNotIn("selected_observation", payload)

    def test_cli_writes_field_evidence_and_dashboard_compatible_d5_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples_path, report_path = write_field_fixture(root)
            output_root = root / "location_field_evidence"
            flywheel_root = root / "data_flywheel"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = field.main(
                    [
                        "--samples",
                        str(samples_path),
                        "--d1-report",
                        str(report_path),
                        "--output-root",
                        str(output_root),
                        "--flywheel-output-root",
                        str(flywheel_root),
                        "--run-id",
                        "unit-field-evidence",
                        "--flywheel-run-id",
                        "unit-field-evidence-data-flywheel",
                        "--generated-at",
                        "2026-07-09T13:00:00+00:00",
                        "--json",
                    ]
                )
            written = json.loads(stdout.getvalue())
            dashboard = message_hub.load_latest_data_flywheel_status(flywheel_root)
            field_report_exists = (output_root / "unit-field-evidence" / field.FIELD_EVIDENCE_JSON).exists()
            d5_status_exists = (
                flywheel_root
                / "unit-field-evidence-data-flywheel"
                / flywheel.STATUS_JSON
            ).exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(written["run_id"], "unit-field-evidence")
        self.assertTrue(field_report_exists)
        self.assertTrue(d5_status_exists)
        self.assertTrue(dashboard["available"])
        self.assertEqual(dashboard["counts"]["location_field_evidence_reports"], 1)
        self.assertEqual(dashboard["counts"]["field_samples"], 3)
        self.assertEqual(dashboard["counts"]["field_gnss_fix_samples"], 1)
        self.assertEqual(dashboard["counts"]["field_gnss_no_fix_samples"], 1)
        self.assertEqual(dashboard["counts"]["field_unique_cell_count"], 2)
        self.assertEqual(dashboard["review_queue"]["pending_records"], 6)
        self.assertFalse(dashboard["readiness"]["model_training_ready"])
        payload = json.dumps({"written": written, "dashboard": dashboard}, ensure_ascii=False)
        self.assertNotIn(f"{BASE_LAT:.6f}", payload)
        self.assertNotIn(f"{BASE_LON:.6f}", payload)
        self.assertNotIn("private-cell-alpha", payload)
        self.assertNotIn("private-cell-beta", payload)


if __name__ == "__main__":
    unittest.main()
