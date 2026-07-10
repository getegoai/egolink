from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import run_training_experiment_preflight


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dataset_manifest(*, synthetic: bool = False, incomplete: bool = False) -> dict[str, object]:
    record = {
        "record_id": "cand-001",
        "session_id": "session-001",
        "candidate_type": "uncertain",
        "label": "needs_help",
        "split_name": "train",
        "source_status": "synthetic_generated" if synthetic else "verified",
        "source_manifest_hash": "abc123",
    }
    if incomplete:
        record.pop("source_manifest_hash")
    return {
        "schema_version": "egolink.training_dataset_manifest.v0.1",
        "builder_version": "train-001.0",
        "dataset_id": "unit-ready-dataset",
        "generated_at": "2026-07-05T11:00:00+00:00",
        "status": "ready_for_training_handoff",
        "reason": "reviewed_candidates_available",
        "counts": {
            "records_total": 1,
            "eligible_records": 1,
            "reviewed_training_candidate_records": 1,
        },
        "split_counts": {"train": 1},
        "records": [record],
        "training_server": {
            "ready_for_handoff": True,
            "runner_integration": "not_integrated",
            "experiment_id": None,
        },
    }


def experiment_plan(*, ready: bool = True) -> dict[str, object]:
    return {
        "schema_version": "egolink.training_experiment_plan.v0.1",
        "builder_version": "train-002.0",
        "experiment_id": "unit-experiment",
        "created_at": "2026-07-05T11:01:00+00:00",
        "status": "ready_for_runner" if ready else "blocked_dataset_not_ready",
        "reason": "reviewed_dataset_manifest_available" if ready else "candidate_store_missing",
        "dataset": {
            "dataset_id": "unit-ready-dataset",
            "manifest_status": "ready_for_training_handoff" if ready else "not_ready",
            "manifest_reason": "reviewed_candidates_available" if ready else "candidate_store_missing",
            "manifest_ref": "training_dataset_manifest.json",
            "records_total": 1 if ready else 0,
            "eligible_records": 1 if ready else 0,
            "reviewed_training_candidate_records": 1 if ready else 0,
            "split_counts": {"train": 1} if ready else {},
            "record_sample": [],
        },
        "model_track": {
            "track": "motionnet",
            "candidate_model": "motionnet-v0.1-planned",
            "baseline_model": "m0_rule_router",
        },
        "runner": {
            "integration": "not_integrated",
            "ready_for_handoff": ready,
            "training_server_endpoint": None,
            "next_command": "Integrate a runner task.",
        },
        "metrics_plan": {
            "classification": {"accuracy": "planned_not_measured"},
            "operations": {"latency_ms": "planned_not_measured"},
        },
        "gates": {
            "dataset_ready": ready,
            "baseline_comparison": "planned_not_run",
            "footprint": "planned_not_measured",
            "power": "planned_not_measured",
        },
    }


class TrainingExperimentPreflightTests(unittest.TestCase):
    def run_preflight(self, args: list[str]) -> tuple[int, dict[str, object]]:
        with redirect_stdout(StringIO()) as output:
            exit_code = run_training_experiment_preflight.main(args + ["--json"])
        return exit_code, json.loads(output.getvalue())

    def test_blocked_experiment_plan_is_not_runner_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "inputs" / "training_experiment_plan.json"
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            output_root = root / "preflight"
            write_json(plan_path, experiment_plan(ready=False))
            write_json(manifest_path, dataset_manifest())

            exit_code, payload = self.run_preflight(
                [
                    "--experiment-plan",
                    str(plan_path),
                    "--dataset-manifest",
                    str(manifest_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-blocked-preflight",
                    "--created-at",
                    "2026-07-05T11:05:00+00:00",
                    "--require-ready",
                ]
            )
            payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["schema_version"], "egolink.training_run_preflight.v0.1")
        self.assertEqual(payload["status"], "blocked_experiment_not_ready")
        self.assertFalse(payload["runner"]["ready_for_training_runner"])
        self.assertNotIn(str(plan_path), payload_text)
        self.assertNotIn(str(manifest_path), payload_text)
        self.assertNotIn("record_json", payload_text)
        self.assertNotIn("raw_payload", payload_text)

    def test_synthetic_records_require_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "inputs" / "training_experiment_plan.json"
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            output_root = root / "preflight"
            write_json(plan_path, experiment_plan())
            write_json(manifest_path, dataset_manifest(synthetic=True))

            exit_code, payload = self.run_preflight(
                [
                    "--experiment-plan",
                    str(plan_path),
                    "--dataset-manifest",
                    str(manifest_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-synthetic-blocked",
                    "--created-at",
                    "2026-07-05T11:06:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_synthetic_without_ack")
        self.assertEqual(payload["dataset"]["synthetic_records"], 1)
        self.assertEqual(payload["checks"]["synthetic_record_policy"], "blocked")
        self.assertEqual(payload["gates"]["model_training"], "not_run")

    def test_allow_synthetic_ready_is_preflight_only_with_no_measured_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "inputs" / "training_experiment_plan.json"
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            output_root = root / "preflight"
            write_json(plan_path, experiment_plan())
            write_json(manifest_path, dataset_manifest(synthetic=True))

            exit_code, payload = self.run_preflight(
                [
                    "--experiment-plan",
                    str(plan_path),
                    "--dataset-manifest",
                    str(manifest_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-synthetic-ready",
                    "--created-at",
                    "2026-07-05T11:07:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )
            report_exists = (output_root / "unit-synthetic-ready" / "training_run_preflight.json").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready_for_training_runner")
        self.assertTrue(payload["runner"]["ready_for_training_runner"])
        self.assertEqual(payload["dataset"]["eligible_records"], 1)
        self.assertEqual(payload["checks"]["synthetic_record_policy"], "acknowledged")
        self.assertEqual(payload["metrics_plan"]["measured"]["classification"], "not_run")
        self.assertEqual(payload["gates"]["model_artifact"], "not_produced")
        self.assertIn("No model training has run.", payload["non_claims"])
        self.assertTrue(report_exists)

    def test_incomplete_dataset_record_blocks_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "inputs" / "training_experiment_plan.json"
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            output_root = root / "preflight"
            write_json(plan_path, experiment_plan())
            write_json(manifest_path, dataset_manifest(incomplete=True))

            exit_code, payload = self.run_preflight(
                [
                    "--experiment-plan",
                    str(plan_path),
                    "--dataset-manifest",
                    str(manifest_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-incomplete-blocked",
                    "--created-at",
                    "2026-07-05T11:08:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_incomplete_dataset_records")
        self.assertEqual(payload["checks"]["missing_record_fields"], {"source_manifest_hash": 1})


if __name__ == "__main__":
    unittest.main()
