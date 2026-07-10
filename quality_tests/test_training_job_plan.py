from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import create_training_job_plan


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_handoff(root: Path, *, status: str = "ready_for_training_server_handoff", synthetic: bool = False) -> Path:
    path = root / "training_handoff_bundle.json"
    write_json(
        path,
        {
            "schema_version": "egolink.training_handoff_bundle.v0.1",
            "handoff_id": "unit-handoff",
            "created_at": "2026-07-06T02:00:00+00:00",
            "status": status,
            "reason": "unit_reason",
            "source_refs": {
                "training_feature_rows": {
                    "ref": "reports/training_features/unit/training_feature_rows.jsonl",
                    "sha256": "abc123",
                    "bytes": 64,
                    "content_copied": False,
                    "private_row": {"target": "secret"},
                }
            },
            "dataset": {
                "dataset_id": "unit-dataset",
                "status": "ready_for_training_handoff",
                "eligible_records": 1,
                "split_counts": {"train": 1},
            },
            "feature_manifest": {
                "feature_set_id": "unit-features",
                "status": "ready_for_feature_runner",
                "feature_scope": "manifest_summary_features",
                "target_separated_from_features": True,
            },
            "feature_rows": {
                "row_count": 1,
                "content_copied": False,
                "raw_rows_exposed": False,
                "rows": [{"target": {"label": "secret"}, "features": {"candidate": "secret"}}],
            },
            "baseline_eval": {
                "eval_id": "unit-eval",
                "status": "baseline_eval_complete",
                "metric_scope": "reviewed_engineering_dataset",
                "product_performance_claim": False,
            },
            "training_server": {
                "integration": "not_configured",
                "endpoint": "https://private.example.invalid/train",
            },
            "checks": {
                "source_ids_match": True,
                "feature_row_count_matches": True,
                "synthetic_input_seen": synthetic,
                "synthetic_policy": "acknowledged" if synthetic else "not_present",
            },
            "gates": {
                "training_handoff": "pass" if status == "ready_for_training_server_handoff" else "blocked",
                "model_training": "not_run",
                "model_artifact": "not_produced",
                "release_claim": "not_allowed",
            },
        },
    )
    return path


class TrainingJobPlanTests(unittest.TestCase):
    def run_job(self, handoff_path: Path, output_root: Path, *extra_args: str) -> tuple[int, dict[str, object]]:
        args = [
            "--handoff-bundle",
            str(handoff_path),
            "--output-root",
            str(output_root),
            "--job-id",
            "unit-job",
            "--created-at",
            "2026-07-06T02:30:00+00:00",
            "--json",
        ]
        with redirect_stdout(StringIO()) as output:
            exit_code = create_training_job_plan.main(args + list(extra_args))
        return exit_code, json.loads(output.getvalue())

    def test_ready_handoff_writes_runner_queue_plan_without_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = write_handoff(root / "inputs")
            exit_code, payload = self.run_job(handoff_path, root / "jobs", "--require-ready")
            plan_exists = (root / "jobs" / "unit-job" / "training_job_plan.json").is_file()
            payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.training_job_plan.v0.1")
        self.assertEqual(payload["status"], "ready_for_runner_queue")
        self.assertEqual(payload["source_handoff"]["handoff_id"], "unit-handoff")
        self.assertEqual(payload["feature_input"]["row_count"], 1)
        self.assertFalse(payload["feature_input"]["row_contents_copied"])
        self.assertFalse(payload["feature_input"]["raw_rows_exposed"])
        self.assertEqual(payload["runner_plan"]["training_server_integration"], "not_configured")
        self.assertIsNone(payload["runner_plan"]["training_server_endpoint"])
        self.assertEqual(payload["gates"]["model_training"], "not_run")
        self.assertEqual(payload["gates"]["model_artifact"], "not_produced")
        self.assertTrue(plan_exists)
        self.assertNotIn("private.example", payload_text)
        self.assertNotIn("private_row", payload_text)
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn('"features"', payload_text)

    def test_synthetic_handoff_requires_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = write_handoff(
                root / "inputs",
                status="synthetic_handoff_dry_run_only",
                synthetic=True,
            )
            exit_code, payload = self.run_job(handoff_path, root / "jobs")
            ack_exit_code, ack_payload = self.run_job(handoff_path, root / "jobs_ack", "--allow-synthetic")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "blocked_synthetic_without_ack")
        self.assertEqual(payload["checks"]["synthetic_policy"], "blocked")
        self.assertEqual(ack_exit_code, 0)
        self.assertEqual(ack_payload["status"], "synthetic_runner_queue_dry_run_only")
        self.assertTrue(ack_payload["runner_plan"]["dry_run_only"])
        self.assertEqual(ack_payload["gates"]["training_job"], "dry_run_only")

    def test_blocked_handoff_does_not_enter_runner_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = write_handoff(root / "inputs", status="blocked_feature_rows_mismatch")
            exit_code, payload = self.run_job(handoff_path, root / "jobs")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "blocked_handoff_not_ready")
        self.assertFalse(payload["runner_plan"]["bundle_ready_for_future_runner"])
        self.assertEqual(payload["gates"]["training_job"], "blocked")


if __name__ == "__main__":
    unittest.main()
