from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from quality_tests import test_a0_imu_calibration as base
from scripts import compare_a0_imu_calibrations as compare


def build_artifact(*, run_suffix: str, gyro_shift: int = 0, accel_shift: int = 0) -> dict:
    """Build a real-shaped artifact from the calibration fixture, optionally perturbed."""
    metadata = base.fixture_metadata()
    metadata["calibration_run_id"] = f"A0-001-SYNTHETIC-{run_suffix}"
    metadata["source_windows"] = {
        role: f"imuw-cmd-{run_suffix}-{index:02d}-b7"
        for index, role in enumerate(base.calibration.SOURCE_ROLES)
    }
    rows = base.fixture_rows(metadata)
    for index, row in enumerate(rows):
        row["capture_cmd_id"] = f"cmd-{run_suffix}-{index:02d}"
        row["window_id"] = metadata["source_windows"][base.calibration.SOURCE_ROLES[index]]
        if gyro_shift or accel_shift:
            for sample in row["samples"]:
                for axis in range(3):
                    sample["gyro_mdps"][axis] += gyro_shift
                    sample["accel_mg"][axis] += accel_shift
        row["samples_sha256"] = base.hashlib.sha256(
            base.calibration.encode_source_samples(row["samples"], window_id=row["window_id"])
        ).hexdigest()
    artifact, _windows, _jsonl, _report = base.calibration.build_calibration_outputs(metadata, rows)
    return artifact


class A0CalibrationRepeatabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = build_artifact(run_suffix="001")

    def test_identical_configuration_reports_zero_deltas(self) -> None:
        repeat = build_artifact(run_suffix="002")
        result = compare.compare_calibrations(self.baseline, repeat)

        self.assertEqual(result["runs_compared"], 2)
        self.assertTrue(result["within_all_proposed_bounds"])
        for section in ("accel_bias_mg", "accel_sensitivity_mg_per_g", "gyro_bias_mdps"):
            for entry in result[section]:
                self.assertEqual(entry["delta"], 0, f"{section}.{entry['axis']}")

    def test_never_claims_repeatability_is_characterized(self) -> None:
        repeat = build_artifact(run_suffix="002")
        result = compare.compare_calibrations(self.baseline, repeat)
        report = compare.format_report(result)

        self.assertFalse(result["repeatability_characterized"])
        self.assertGreaterEqual(result["characterization_requires_runs"], 3)
        self.assertEqual(
            result["proposed_bounds"]["status"],
            "proposed_engineering_observation_bounds_not_validated",
        )
        self.assertIn("not**", report)
        self.assertIn("not a validated specification", report)
        self.assertIn("two_runs_give_one_delta_not_a_distribution", result["limitations"])

    def test_divergent_gyro_bias_is_flagged_not_averaged(self) -> None:
        repeat = build_artifact(run_suffix="002", gyro_shift=900)
        result = compare.compare_calibrations(self.baseline, repeat)

        self.assertFalse(result["checks"]["gyro_bias_within_proposed_bound"])
        self.assertFalse(result["within_all_proposed_bounds"])
        self.assertTrue(all(entry["delta"] == 900 for entry in result["gyro_bias_mdps"]))
        # An out-of-bound comparison still reports numbers rather than refusing or smoothing.
        self.assertTrue(result["checks"]["sensitivity_within_proposed_bound"])

    def test_comparing_an_artifact_with_itself_fails_closed(self) -> None:
        with self.assertRaisesRegex(compare.CalibrationComparisonError, "same calibration"):
            compare.compare_calibrations(self.baseline, copy.deepcopy(self.baseline))

    def test_shared_source_windows_fail_closed(self) -> None:
        repeat = build_artifact(run_suffix="002")
        repeat["source_windows"][0]["window_id"] = self.baseline["source_windows"][0]["window_id"]
        with self.assertRaisesRegex(compare.CalibrationComparisonError, "share source windows"):
            compare.compare_calibrations(self.baseline, repeat)

    def test_different_mounting_or_device_fails_closed(self) -> None:
        repeat = build_artifact(run_suffix="002")
        repeat["mounting"]["mounting_profile_id"] = "some-other-mounting"
        with self.assertRaisesRegex(compare.CalibrationComparisonError, "mounting_profile_id differs"):
            compare.compare_calibrations(self.baseline, repeat)

        repeat = build_artifact(run_suffix="003")
        repeat["device"]["device_id"] = "some-other-device"
        with self.assertRaisesRegex(compare.CalibrationComparisonError, "device_id differs"):
            compare.compare_calibrations(self.baseline, repeat)

    def test_cli_writes_summary_and_report(self) -> None:
        repeat = build_artifact(run_suffix="002")
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            baseline_path = temp_dir / "baseline.json"
            repeat_path = temp_dir / "repeat.json"
            baseline_path.write_text(json.dumps(self.baseline), encoding="utf-8")
            repeat_path.write_text(json.dumps(repeat), encoding="utf-8")
            out_dir = temp_dir / "out"
            code = compare.main(
                [
                    "--baseline", str(baseline_path),
                    "--repeat", str(repeat_path),
                    "--output-dir", str(out_dir),
                    "--json",
                ]
            )
            self.assertEqual(code, 0)
            summary = json.loads((out_dir / "imu_calibration_repeatability.json").read_text(encoding="utf-8"))
            report = (out_dir / "imu_calibration_repeatability.md").read_text(encoding="utf-8")

        self.assertFalse(summary["repeatability_characterized"])
        self.assertIn("Repeatability Comparison", report)

    def test_non_artifact_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            path = Path(temp_dir_raw) / "not_an_artifact.json"
            path.write_text(json.dumps({"schema_version": "something.else"}), encoding="utf-8")
            with self.assertRaisesRegex(compare.CalibrationComparisonError, "not an"):
                compare.load_artifact(path)


if __name__ == "__main__":
    unittest.main()
