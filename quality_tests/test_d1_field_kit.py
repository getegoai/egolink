from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import prepare_d1_field_kit as field_kit


FIXED_CREATED_AT = "2026-07-04T12:00:00+00:00"


class D1FieldKitTests(unittest.TestCase):
    def test_board_matrix_keeps_calling_and_sms_unverified(self) -> None:
        matrix = (Path(__file__).resolve().parents[1] / "docs" / "hardware" / "BOARD_MATRIX.md").read_text(
            encoding="utf-8"
        )
        required_terms = [
            "Cellular Calling/SMS Boundary",
            "Voice calling and SMS are `unverified`",
            "no implemented",
            "no accepted ATD/ATA/CMGS evidence",
            "operator-approved",
            "hardware task",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, matrix)

    def test_default_cli_writes_offline_field_kit_without_secret_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            token_file = tmp_path / "token.txt"
            token_file.write_text("unit-super-secret-token\n", encoding="utf-8")
            output_dir = tmp_path / "kit"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = field_kit.main(
                    [
                        "--run-id",
                        "D1-FIELD-unit",
                        "--hub-url",
                        "http://example.test:8790",
                        "--token-file",
                        str(token_file),
                        "--amoled-port",
                        "COM9",
                        "--output-dir",
                        str(output_dir),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(summary["ok"])
            manifest = json.loads((output_dir / field_kit.MANIFEST_JSON).read_text(encoding="utf-8"))
            runbook = (output_dir / field_kit.RUNBOOK_MD).read_text(encoding="utf-8")
            checklist = (output_dir / field_kit.CHECKLIST_MD).read_text(encoding="utf-8")
            notes = (output_dir / field_kit.NOTES_MD).read_text(encoding="utf-8")

            self.assertEqual(manifest["kit_version"], field_kit.KIT_VERSION)
            self.assertEqual(manifest["power"]["max17048_sda_gpio"], 15)
            self.assertEqual(manifest["power"]["max17048_scl_gpio"], 16)
            self.assertFalse(manifest["scope"]["hardware_contacted"])
            self.assertFalse(manifest["scope"]["message_hub_contacted"])
            self.assertFalse(manifest["scope"]["firmware_flashed"])
            self.assertFalse(manifest["secrets"]["token_value_read"])
            self.assertEqual(manifest["sidecar"]["amoled_port"], "COM9")
            self.assertEqual(manifest["sidecar"]["status_command"], "display_status")
            self.assertFalse(manifest["sidecar"]["product_dependency"])
            self.assertEqual(manifest["communications"]["voice_calling"], "unverified_not_implemented")
            self.assertEqual(manifest["communications"]["sms"], "unverified_not_implemented")
            self.assertFalse(manifest["communications"]["live_call_or_sms_probe_included"])
            self.assertIn("preflight_web_api_gate", manifest["commands"])
            self.assertIn("preflight_amoled_visible_status", manifest["commands"])
            self.assertIn("live_field_companion", manifest["commands"])
            self.assertIn("post_run_collect_evidence", manifest["commands"])
            self.assertIn("post_run_sync_dashboard_summaries", manifest["commands"])
            self.assertNotIn("post_run_data_flywheel_status", manifest["commands"])
            self.assertIn(
                "scripts\\run_amoled_d1_status_sidecar.ps1",
                manifest["commands"]["preflight_amoled_visible_status"]["argv"],
            )
            self.assertIn("display_status", runbook)
            self.assertIn("scripts\\run_d1_field_companion.ps1", manifest["commands"]["live_field_companion"]["argv"])
            self.assertIn("-AmoledPort", manifest["commands"]["live_field_companion"]["argv"])
            self.assertIn("COM9", manifest["commands"]["live_field_companion"]["argv"])
            self.assertIn("-PrepareBuild", manifest["commands"]["prepare_build"]["argv"])
            self.assertNotIn("-Flash", manifest["commands"]["prepare_build"]["argv"])
            self.assertIn("-EnableD1PeriodicLocation", manifest["commands"]["prepare_build"]["argv"])
            self.assertIn("-D1PeriodicLocationIntervalSec", manifest["commands"]["prepare_build"]["argv"])
            self.assertIn("60", manifest["commands"]["prepare_build"]["argv"])
            self.assertIn("-LteCommandName", manifest["commands"]["short_usb_free_link_check"]["argv"])
            self.assertIn("request_location", manifest["commands"]["short_usb_free_link_check"]["argv"])
            self.assertIn("scripts\\observe_d1_field_run.py", manifest["commands"]["live_field_observer"]["argv"])
            self.assertIn("--duration-minutes", manifest["commands"]["live_field_observer"]["argv"])
            self.assertIn("--poll-interval-sec", manifest["commands"]["live_field_observer"]["argv"])
            self.assertIn("--max-stale-sec", manifest["commands"]["live_field_observer"]["argv"])
            collector_argv = manifest["commands"]["post_run_collect_evidence"]["argv"]
            self.assertIn("scripts\\collect_d1_postrun.py", collector_argv)
            self.assertIn("--message-test-run-id", collector_argv)
            self.assertIn("D1-FIELD-unit", collector_argv)
            self.assertIn("--field-observation-report", collector_argv)
            self.assertIn("reports\\d1_field_observation\\D1-FIELD-unit\\d1_field_observation_report.json", collector_argv)
            self.assertIn("--field-observation-status", collector_argv)
            self.assertIn("reports\\d1_field_observation\\D1-FIELD-unit\\d1_field_observation_status.json", collector_argv)
            self.assertIn("--skip-data-flywheel", collector_argv)
            self.assertIn("--skip-training-chain", collector_argv)
            self.assertIn("--skip-training-readiness", collector_argv)
            self.assertIn("--skip-labeling-intake", collector_argv)
            self.assertIn("--skip-labeling-queue", collector_argv)
            self.assertIn("--skip-labeling-review-packet", collector_argv)
            self.assertIn("--skip-labeling-decision-template", collector_argv)
            self.assertIn("--skip-labeling-decision-validation", collector_argv)
            self.assertNotIn("--data-pipeline-run-id", collector_argv)
            self.assertNotIn("--labeling-review-packet-output-root", collector_argv)
            self.assertNotIn("scripts\\run_data_flywheel_pipeline.py", json.dumps(manifest["commands"]))
            sync_argv = manifest["commands"]["post_run_sync_dashboard_summaries"]["argv"]
            self.assertIn("scripts\\deploy_message_hub_vps.ps1", sync_argv)
            self.assertIn("-IncludeFieldReportSummaries", sync_argv)
            self.assertNotIn("-IncludeDataFlywheelSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingExperimentSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingRunSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingFeatureSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingRunnerDryRunSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingBaselineEvalSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingHandoffSummaries", sync_argv)
            self.assertNotIn("-IncludeTrainingJobSummaries", sync_argv)
            self.assertNotIn("-IncludeSyntheticTrainingChainSummaries", sync_argv)
            self.assertNotIn("-IncludeD1TrainingReadinessSummaries", sync_argv)
            self.assertNotIn("-IncludeD1LabelingIntakeSummaries", sync_argv)
            self.assertNotIn("-IncludeD1LabelingQueueSummaries", sync_argv)
            self.assertNotIn("-IncludeD1LabelingReviewSummaries", sync_argv)
            self.assertNotIn("-IncludeD1LabelingDecisionSummaries", sync_argv)
            self.assertTrue(manifest["commands"]["flash_explicit_operator_action"]["hardware_action"])
            self.assertTrue(manifest["commands"]["short_usb_free_link_check"]["sends_message_hub_command"])
            self.assertTrue(manifest["commands"]["preflight_amoled_visible_status"]["writes_amoled_serial"])
            self.assertFalse(manifest["commands"]["preflight_amoled_visible_status"]["sends_message_hub_command"])
            self.assertTrue(manifest["commands"]["live_field_companion"]["writes_amoled_serial"])
            self.assertFalse(manifest["commands"]["live_field_companion"]["sends_message_hub_command"])
            self.assertFalse(manifest["commands"]["live_field_observer"].get("hardware_action", False))
            self.assertFalse(manifest["commands"]["post_run_collect_evidence"].get("hardware_action", False))
            self.assertFalse(manifest["commands"]["post_run_collect_evidence"].get("sends_message_hub_command", False))
            self.assertIn("field_observation_report", manifest["expected_outputs"])
            self.assertIn("field_observation_status", manifest["expected_outputs"])
            self.assertIn("companion_summary", manifest["expected_outputs"])
            self.assertIn("amoled_sidecar_summary", manifest["expected_outputs"])
            self.assertIn("postrun_summary", manifest["expected_outputs"])
            self.assertIn("web_api_report", manifest["expected_outputs"])
            self.assertIn("power_report", manifest["expected_outputs"])
            self.assertIn("d1_demo_report", manifest["expected_outputs"])
            self.assertIn("message_hub_export", manifest["expected_outputs"])
            self.assertNotIn("data_flywheel_pipeline", manifest["expected_outputs"])
            self.assertNotIn("data_flywheel_status", manifest["expected_outputs"])
            self.assertNotIn("training_dataset_manifest", manifest["expected_outputs"])
            self.assertNotIn("training_experiment_plan", manifest["expected_outputs"])
            self.assertNotIn("training_run_preflight", manifest["expected_outputs"])
            self.assertNotIn("training_feature_manifest", manifest["expected_outputs"])
            self.assertNotIn("training_runner_dry_run", manifest["expected_outputs"])
            self.assertNotIn("training_baseline_eval", manifest["expected_outputs"])
            self.assertNotIn("training_handoff_bundle", manifest["expected_outputs"])
            self.assertNotIn("training_job_plan", manifest["expected_outputs"])
            self.assertNotIn("d1_training_readiness", manifest["expected_outputs"])
            self.assertNotIn("d1_labeling_intake", manifest["expected_outputs"])
            self.assertNotIn("d1_labeling_queue", manifest["expected_outputs"])
            self.assertNotIn("d1_labeling_review_packet", manifest["expected_outputs"])
            self.assertNotIn("d1_labeling_decision_template", manifest["expected_outputs"])
            self.assertNotIn("d1_labeling_decision_validation", manifest["expected_outputs"])
            self.assertEqual(manifest["acceptance"]["status"], "pending_founder_review")
            self.assertEqual(manifest["acceptance"]["tag"], "v0.1.0")
            self.assertIn("D1-FIELD-unit", manifest["acceptance"]["required_report"])
            self.assertIn("D1 link-through accepted", manifest["acceptance"]["tag_command"])
            self.assertIn("frozen until D2 is accepted", " ".join(manifest["boundaries"]))
            self.assertIn("calling_not_claimed", manifest["non_claims"])
            self.assertIn("sms_not_claimed", manifest["non_claims"])
            self.assertIn("model_training_not_claimed", manifest["non_claims"])
            self.assertIn("model_metrics_not_claimed", manifest["non_claims"])

            combined = json.dumps(manifest) + runbook + checklist + notes + stdout.getvalue()
            self.assertNotIn("unit-super-secret-token", combined)
            self.assertNotIn("*.db", combined)
            self.assertNotIn("*.jsonl", manifest["commands"]["post_run_sync_dashboard_summaries"]["powershell"])
            self.assertIn("D1 Outdoor Field Runbook", runbook)
            self.assertIn("Preflight AMOLED Visible Status", runbook)
            self.assertIn("Preferred one-command live run", runbook)
            self.assertIn("Recommended Post-Run Collector", runbook)
            self.assertIn("scripts\\collect_d1_postrun.py", runbook)
            self.assertIn("Acceptance Tag", runbook)
            self.assertIn("git tag -a v0.1.0", runbook)
            self.assertNotIn("Data Flywheel Pipeline", runbook)
            self.assertNotIn("D1 training-readiness", runbook)
            self.assertNotIn("D1 labeling-intake", runbook)
            self.assertNotIn("D1 labeling-queue", runbook)
            self.assertNotIn("D1 labeling-review packet", runbook)
            self.assertNotIn("D1 labeling-decision template", runbook)
            self.assertNotIn("D1 labeling-decision validation", runbook)
            self.assertNotIn("TRAIN-003..008", runbook)
            self.assertIn("Sync Dashboard Summaries", runbook)
            self.assertIn("observe_d1_field_run.py", runbook)
            self.assertIn("Live field observation report", notes)
            self.assertIn("AMOLED sidecar summary", notes)
            self.assertIn("Post-run summary", notes)
            self.assertIn("Founder acceptance tag", notes)
            self.assertNotIn("D1 training readiness", notes)
            self.assertNotIn("D1 labeling intake", notes)
            self.assertNotIn("D1 labeling queue", notes)
            self.assertNotIn("D1 labeling review packet", notes)
            self.assertNotIn("D1 labeling decision template", notes)
            self.assertNotIn("D1 labeling decision validation", notes)
            self.assertNotIn("Training run preflight", notes)
            self.assertNotIn("Training baseline eval", notes)
            self.assertNotIn("Training job plan", notes)
            self.assertIn("Before Leaving", checklist)
            self.assertIn("D1 Field Operator Notes", notes)
            self.assertIn("Calling and SMS are not part of this run", checklist)
            self.assertIn("Run the one-command post-run collector", checklist)
            self.assertIn("Do not run data-flywheel, labeling, MODEL-DEVICE, DATA, or TRAIN", checklist)
            self.assertIn("After founder acceptance, create tag v0.1.0", checklist)
            self.assertNotIn("post-run training readiness", checklist)
            self.assertNotIn("D1 labeling queue", checklist)
            self.assertNotIn("D1 review packet", checklist)
            self.assertNotIn("D1 decision template", checklist)
            self.assertNotIn("D1 decision validation", checklist)

    def test_v1_board_uses_recorded_v1_max17048_pins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = field_kit.prepare_field_kit(
                run_id="D1-FIELD-v1",
                output_dir=Path(tmp),
                hub_url="",
                host_name="hub.example",
                port=8790,
                scheme="http",
                device_id="ego-link-r1-connectivity-001",
                board_id="connectivity-node-001",
                fw_version="0.1.0-fw001-hw-r1",
                token_file="server/runtime/vps_message_hub_token.txt",
                amoled_port="",
                duration_hours=3.5,
                location_interval_sec=45,
                board_revision="V1",
                max17048_sda_gpio=None,
                max17048_scl_gpio=None,
                battery_capacity_mah=1200,
                created_at=FIXED_CREATED_AT,
            )

            self.assertEqual(manifest["created_at"], FIXED_CREATED_AT)
            self.assertEqual(manifest["hub"]["hub_url"], "http://hub.example:8790")
            self.assertEqual(manifest["power"]["max17048_sda_gpio"], 3)
            self.assertEqual(manifest["power"]["max17048_scl_gpio"], 2)
            power_argv = manifest["commands"]["post_run_power_curve"]["argv"]
            self.assertIn("--min-duration-hours", power_argv)
            self.assertIn("3.5", power_argv)
            self.assertIn("--battery-capacity-mah", power_argv)
            self.assertIn("1200", power_argv)
            collector_argv = manifest["commands"]["post_run_collect_evidence"]["argv"]
            self.assertIn("--battery-capacity-mah", collector_argv)
            self.assertIn("1200", collector_argv)
            self.assertEqual(manifest["field_run"]["location_interval_sec"], 45)
            prepare_argv = manifest["commands"]["prepare_build"]["argv"]
            self.assertIn("-EnableD1PeriodicLocation", prepare_argv)
            self.assertIn("-D1PeriodicLocationIntervalSec", prepare_argv)
            self.assertIn("45", prepare_argv)
            observer_argv = manifest["commands"]["live_field_observer"]["argv"]
            self.assertIn("--poll-interval-sec", observer_argv)
            self.assertIn("45", observer_argv)
            self.assertIn("post_run_sync_dashboard_summaries", manifest["commands"])
            companion_argv = manifest["commands"]["live_field_companion"]["argv"]
            self.assertIn("scripts\\run_d1_field_companion.ps1", companion_argv)
            self.assertNotIn("-AmoledPort", companion_argv)
            self.assertEqual(manifest["sidecar"]["amoled_port"], "")

    def test_partial_pin_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(field_kit.D1FieldKitError):
                field_kit.prepare_field_kit(
                    run_id="D1-FIELD-bad-pins",
                    output_dir=Path(tmp),
                    hub_url="",
                    host_name="hub.example",
                    port=8790,
                    scheme="http",
                    device_id="ego-link-r1-connectivity-001",
                    board_id="connectivity-node-001",
                    fw_version="0.1.0-fw001-hw-r1",
                    token_file="server/runtime/vps_message_hub_token.txt",
                    amoled_port="",
                    duration_hours=4,
                    location_interval_sec=60,
                    board_revision="V2",
                    max17048_sda_gpio=15,
                    max17048_scl_gpio=None,
                    battery_capacity_mah=None,
                    created_at=FIXED_CREATED_AT,
                )


if __name__ == "__main__":
    unittest.main()
