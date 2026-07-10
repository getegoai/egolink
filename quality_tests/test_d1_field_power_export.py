from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import analyze_power_curve
from scripts import convert_d1_field_samples_to_power_export as converter


FIXED_CREATED_AT = "2026-07-09T04:00:00+00:00"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def sample(
    *,
    index: int,
    battery_mv: int = 4100,
    soc_pct: float = 90.0,
    evidence_status: str = "measured",
) -> dict:
    return {
        "collected_at": f"2026-07-09T0{index}:00:05+00:00",
        "ok": True,
        "device_id": "ego-link-r1-connectivity-001",
        "last_seq": index,
        "last_location_event_type": "location_observation",
        "power_latest_sample_at": f"2026-07-09T0{index}:00:00+00:00",
        "battery_mv": battery_mv,
        "soc_pct": soc_pct,
        "power_evidence_status": evidence_status,
        "cell_lte_seen": True,
        "power_sample_count": index + 1,
        "freshness_s": 5,
        "d1_gate_status": "ready",
    }


class D1FieldPowerExportTests(unittest.TestCase):
    def test_field_samples_convert_to_power_export_for_existing_analyzer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            samples_path = tmp_path / "d1_field_samples.jsonl"
            field_report_path = tmp_path / "d1_field_observation_report.json"
            output_path = tmp_path / "field_observer_power_export.json"
            write_jsonl(
                samples_path,
                [
                    sample(index=0, battery_mv=4100, soc_pct=90.0),
                    sample(index=1, battery_mv=4080, soc_pct=89.0),
                    sample(index=2, battery_mv=4050, soc_pct=88.0),
                ],
            )
            field_report_path.write_text(json.dumps({"run_id": "FIELD-004-unit"}) + "\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = converter.main(
                    [
                        "--samples-jsonl",
                        str(samples_path),
                        "--field-report",
                        str(field_report_path),
                        "--output",
                        str(output_path),
                        "--created-at",
                        FIXED_CREATED_AT,
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            export = payload["export"]
            self.assertTrue(output_path.is_file())
            self.assertEqual(export["test_run"]["id"], "FIELD-004-unit")
            self.assertEqual(export["conversion"]["input_sample_count"], 3)
            self.assertEqual(export["conversion"]["exported_power_message_count"], 3)
            self.assertEqual(export["conversion"]["measured_power_message_count"], 3)
            self.assertFalse(export["conversion"]["scope"]["hardware_contacted"])
            self.assertFalse(export["conversion"]["scope"]["battery_life_claimed"])

            report = analyze_power_curve.evaluate_power_curve(
                export,
                created_at=FIXED_CREATED_AT,
                min_duration_hours=1,
                battery_capacity_mah=1000,
            )
            self.assertEqual(report["result"]["status"], "PASS")
            self.assertEqual(report["counts"]["measured_power_samples"], 3)
            self.assertEqual(report["duration_hours"], 2.0)
            self.assertEqual(report["consumption_estimate"]["status"], "estimated")

    def test_converter_preserves_mock_power_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            samples_path = Path(tmp) / "d1_field_samples.jsonl"
            write_jsonl(
                samples_path,
                [
                    sample(index=0, battery_mv=4100, soc_pct=90.0, evidence_status="mock"),
                    sample(index=1, battery_mv=4090, soc_pct=89.5, evidence_status="mock"),
                ],
            )

            export = converter.build_power_export(
                samples_path=samples_path,
                run_id="FIELD-004-mock",
                created_at=FIXED_CREATED_AT,
            )

            self.assertEqual(export["conversion"]["measured_power_message_count"], 0)
            statuses = {message["power"]["evidence_status"] for message in export["messages"]}
            self.assertEqual(statuses, {"mock"})
            report = analyze_power_curve.evaluate_power_curve(
                export,
                created_at=FIXED_CREATED_AT,
                min_duration_hours=1,
                battery_capacity_mah=1000,
            )
            self.assertEqual(report["result"]["status"], "FAIL")
            self.assertIn("export contains no measured power samples", report["result"]["errors"])


if __name__ == "__main__":
    unittest.main()
