from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import session_inspector
from scripts import generate_synthetic_scenarios


class SyntheticScenarioGeneratorTests(unittest.TestCase):
    def run_generator(self, args: list[str]) -> tuple[int, dict[str, object]]:
        with redirect_stdout(StringIO()) as output:
            exit_code = generate_synthetic_scenarios.main(args + ["--json"])
        return exit_code, json.loads(output.getvalue())

    def test_generates_synthetic_recording_with_training_request_but_no_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            exit_code, payload = self.run_generator(
                [
                    "--output-root",
                    str(root),
                    "--run-id",
                    "unit-synthetic-basic",
                    "--generated-at",
                    "2026-07-05T10:00:00+00:00",
                    "--scenario",
                    "normal_walk",
                ]
            )
            recording_dir = root / "unit-synthetic-basic" / "recordings" / "unit-synthetic-basic-normal_walk-001"
            manifest = json.loads((recording_dir / "session_manifest.json").read_text(encoding="utf-8"))
            annotations = [
                json.loads(line)
                for line in (recording_dir / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            quality = session_inspector.inspect_recording(recording_dir)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "generated")
        self.assertTrue(payload["synthetic_only"])
        self.assertEqual(payload["counts"]["recordings"], 1)
        self.assertEqual(payload["counts"]["training_requested"], 1)
        self.assertFalse(payload["candidate_store"]["written"])
        self.assertEqual(manifest["synthetic"]["schema_version"], "egolink.synthetic_recording_source.v0.1")
        self.assertTrue(manifest["synthetic"]["synthetic_only"])
        self.assertEqual(manifest["synthetic"]["allowed_use"], "pipeline_dry_run_and_integration_testing")
        self.assertEqual(annotations[0]["label"], "safe")
        self.assertTrue(annotations[0]["consent"]["training_allowed"])
        self.assertFalse(annotations[0]["consent"]["raw_audio_allowed"])
        self.assertFalse(annotations[0]["consent"]["raw_image_allowed"])
        self.assertTrue(quality["passed"])

    def test_run_pipeline_ingests_synthetic_recording_as_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "unit-synthetic-pipeline" / "synthetic_candidates.db"

            exit_code, payload = self.run_generator(
                [
                    "--output-root",
                    str(root),
                    "--run-id",
                    "unit-synthetic-pipeline",
                    "--generated-at",
                    "2026-07-05T10:10:00+00:00",
                    "--scenario",
                    "manual_sos",
                    "--run-pipeline",
                ]
            )
            payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "needs_review")
        self.assertEqual(payload["pipelines"]["initial"]["status"], "needs_review")
        self.assertEqual(payload["pipelines"]["initial"]["records_total"], 1)
        self.assertEqual(payload["pipelines"]["initial"]["pending_review"], 1)
        self.assertEqual(payload["pipelines"]["initial"]["dataset_status"], "not_ready")
        self.assertEqual(payload["candidate_store"]["db_ref"], "synthetic_candidates.db")
        self.assertNotIn(str(db_path), payload_text)
        self.assertNotIn("record_json", payload_text)
        self.assertNotIn("raw_payload", payload_text)

    def test_review_synthetic_promotes_only_dry_run_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            exit_code, payload = self.run_generator(
                [
                    "--output-root",
                    str(root),
                    "--run-id",
                    "unit-synthetic-reviewed",
                    "--generated-at",
                    "2026-07-05T10:20:00+00:00",
                    "--scenario",
                    "normal_walk",
                    "--scenario",
                    "no_response",
                    "--review-synthetic",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "synthetic_ready_for_runner")
        self.assertEqual(payload["counts"]["recordings"], 2)
        self.assertEqual(payload["counts"]["reviewed_records"], 2)
        self.assertEqual(payload["pipelines"]["initial"]["status"], "needs_review")
        self.assertEqual(payload["pipelines"]["reviewed"]["status"], "ready_for_training_handoff")
        self.assertEqual(payload["pipelines"]["reviewed"]["eligible_records"], 2)
        self.assertEqual(payload["pipelines"]["reviewed"]["experiment_status"], "ready_for_runner")
        self.assertTrue(payload["pipelines"]["reviewed"]["runner_ready"])
        self.assertTrue(payload["synthetic_review"]["explicit_review_requested"])
        self.assertEqual(payload["synthetic_review"]["failed_reviews"], [])
        self.assertIn("Synthetic scenarios are not hardware, field, or user evidence.", payload["non_claims"])


if __name__ == "__main__":
    unittest.main()
