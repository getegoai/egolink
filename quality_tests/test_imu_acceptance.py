from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import imu_acceptance


def sample_profile(*, production: bool = False) -> dict:
    return {
        "schema_version": "egolink.imu_calibration_profile.v0.1",
        "profile_id": "sample-profile",
        "stage": "production" if production else "engineering",
        "hardware_profile": "esp32-s3-touch-amoled-2.06-qmi8658",
        "production_ready": production,
        "formal_imu_acceptance": production,
        "recalibration_required_after": [
            "imu_mounting_position_change",
            "odr_filter_fifo_or_interrupt_policy_change",
            "power_rail_or_regulator_change",
        ],
    }


def complete_manifest(*, observed_on_hardware: bool = True) -> dict:
    return {
        "schema_version": imu_acceptance.EVIDENCE_SCHEMA_VERSION,
        "evidence": {
            gate["id"]: {
                "status": "pass",
                "artifact": f"docs/hardware/{gate['id']}.md",
                "observed_on_hardware": observed_on_hardware,
            }
            for gate in imu_acceptance.REQUIRED_GATES
        },
    }


class ImuAcceptanceTests(unittest.TestCase):
    def test_engineering_profile_blocks_formal_acceptance(self) -> None:
        report = imu_acceptance.build_acceptance_preflight_report(
            sample_profile(production=False),
            evidence_manifest=complete_manifest(),
            report_id="timu009b-preflight",
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertFalse(report["formal_imu_acceptance"])
        self.assertTrue(report["all_evidence_gates_passed"])
        self.assertIn("calibration_profile_not_production_stage", report["profile_blockers"])
        self.assertIn("calibration_profile_production_ready_false", report["profile_blockers"])
        self.assertFalse(report["motionnet_training_enabled"])

    def test_missing_evidence_manifest_fails_all_required_gates(self) -> None:
        report = imu_acceptance.build_acceptance_preflight_report(
            sample_profile(production=False),
            report_id="timu009b-preflight",
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertFalse(report["all_evidence_gates_passed"])
        self.assertEqual(
            set(report["failed_gates"]),
            {gate["id"] for gate in imu_acceptance.REQUIRED_GATES},
        )
        self.assertTrue(all(gate["reason"] == "evidence_missing" for gate in report["gate_results"]))

    def test_evidence_must_be_observed_on_hardware(self) -> None:
        report = imu_acceptance.build_acceptance_preflight_report(
            sample_profile(production=True),
            evidence_manifest=complete_manifest(observed_on_hardware=False),
            report_id="timu009b-preflight",
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertFalse(report["formal_imu_acceptance"])
        self.assertFalse(report["all_evidence_gates_passed"])
        self.assertTrue(all(gate["reason"] == "hardware_observation_missing" for gate in report["gate_results"]))

    def test_production_profile_with_complete_hardware_evidence_can_pass_preflight(self) -> None:
        report = imu_acceptance.build_acceptance_preflight_report(
            sample_profile(production=True),
            evidence_manifest=complete_manifest(),
            report_id="timu009b-preflight",
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertTrue(report["all_evidence_gates_passed"])
        self.assertTrue(report["formal_imu_acceptance"])
        self.assertEqual(report["profile_blockers"], [])
        self.assertEqual(report["failed_gates"], [])

    def test_evidence_manifest_template_lists_all_gates_as_pending(self) -> None:
        manifest = imu_acceptance.build_evidence_manifest_template(
            manifest_id="timu009c-b0-template",
            hardware_profile="esp32-s3-touch-amoled-2.06-qmi8658",
            calibration_profile_id="sample-profile",
            target_mounting_direction="pending-final-wearable-orientation",
            reference_artifacts=["docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md"],
            generated_at="2026-06-24T00:00:00+00:00",
        )

        self.assertEqual(manifest["schema_version"], imu_acceptance.EVIDENCE_SCHEMA_VERSION)
        self.assertEqual(manifest["target_mounting_direction"], "pending-final-wearable-orientation")
        self.assertFalse(manifest["boundary"]["formal_imu_acceptance"])
        self.assertEqual(
            set(manifest["evidence"]),
            {gate["id"] for gate in imu_acceptance.REQUIRED_GATES},
        )
        self.assertTrue(all(row["status"] == "pending" for row in manifest["evidence"].values()))
        self.assertTrue(all(row["observed_on_hardware"] is False for row in manifest["evidence"].values()))
        markdown = imu_acceptance.format_evidence_manifest_markdown(manifest)
        self.assertIn("# TIMU-009C-B0 IMU Product Mounting Evidence Template", markdown)
        self.assertIn("Do not set a gate to `pass`", markdown)

    def test_cli_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path = root / "profile.json"
            output_json = root / "preflight.json"
            markdown_path = root / "preflight.md"
            profile_path.write_text(json.dumps(sample_profile()), encoding="utf-8")

            exit_code = imu_acceptance.main(
                [
                    "--calibration-profile",
                    str(profile_path),
                    "--report-id",
                    "timu009b-preflight",
                    "--output-json",
                    str(output_json),
                    "--markdown",
                    str(markdown_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            report = json.loads(output_json.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertFalse(report["formal_imu_acceptance"])
            self.assertIn("# TIMU-009B IMU Product Acceptance Preflight", markdown)
            self.assertIn("Formal IMU acceptance: `False`", markdown)

    def test_cli_writes_evidence_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path = root / "profile.json"
            template_json = root / "evidence-template.json"
            template_markdown = root / "evidence-template.md"
            profile_path.write_text(json.dumps(sample_profile()), encoding="utf-8")

            exit_code = imu_acceptance.main(
                [
                    "--calibration-profile",
                    str(profile_path),
                    "--report-id",
                    "timu009c-b0",
                    "--evidence-template-json",
                    str(template_json),
                    "--evidence-template-markdown",
                    str(template_markdown),
                    "--manifest-id",
                    "timu009c-b0-template",
                    "--target-mounting-direction",
                    "pending-final-wearable-orientation",
                    "--reference-artifact",
                    "docs/hardware/TIMU_009C_QMI8658_BACKEND_READINESS_CAPTURE_20260624.md",
                ]
            )

            self.assertEqual(exit_code, 0)
            manifest = json.loads(template_json.read_text(encoding="utf-8"))
            markdown = template_markdown.read_text(encoding="utf-8")
            self.assertEqual(manifest["manifest_id"], "timu009c-b0-template")
            self.assertEqual(manifest["evidence"]["product_mounting_direction_frozen"]["status"], "pending")
            self.assertIn("TIMU-009C-B0", markdown)
            self.assertIn("pending-final-wearable-orientation", markdown)


if __name__ == "__main__":
    unittest.main()
