from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import register_training_experiment


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def not_ready_manifest() -> dict[str, object]:
    return {
        "schema_version": "egolink.training_dataset_manifest.v0.1",
        "builder_version": "train-001.0",
        "dataset_id": "unit-empty-dataset",
        "generated_at": "2026-07-05T06:00:00+00:00",
        "status": "not_ready",
        "reason": "candidate_store_missing",
        "counts": {
            "records_total": 0,
            "eligible_records": 0,
            "reviewed_training_candidate_records": 0,
        },
        "split_counts": {},
        "records": [],
        "training_server": {
            "ready_for_handoff": False,
            "runner_integration": "not_integrated",
            "experiment_id": None,
        },
    }


def ready_manifest() -> dict[str, object]:
    return {
        "schema_version": "egolink.training_dataset_manifest.v0.1",
        "builder_version": "train-001.0",
        "dataset_id": "unit-ready-dataset",
        "generated_at": "2026-07-05T06:05:00+00:00",
        "status": "ready_for_training_handoff",
        "reason": "reviewed_candidates_available",
        "counts": {
            "records_total": 1,
            "eligible_records": 1,
            "reviewed_training_candidate_records": 1,
        },
        "split_counts": {"train": 1},
        "records": [
            {
                "record_id": "record-001",
                "session_id": "session-001",
                "candidate_type": "sos_confirmation",
                "label": "needs_help",
                "split_name": "train",
                "source_manifest_hash": "abc123",
            }
        ],
        "training_server": {
            "ready_for_handoff": True,
            "runner_integration": "not_integrated",
            "experiment_id": None,
        },
    }


class TrainingExperimentRegistryTests(unittest.TestCase):
    def test_cli_writes_blocked_plan_without_manifest_path_or_raw_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "source" / "training_dataset_manifest.json"
            output_root = root / "plans"
            write_manifest(manifest_path, not_ready_manifest())

            with redirect_stdout(StringIO()) as output:
                exit_code = register_training_experiment.main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--output-root",
                        str(output_root),
                        "--experiment-id",
                        "unit-blocked-experiment",
                        "--created-at",
                        "2026-07-05T06:10:00+00:00",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            plan_exists = (output_root / "unit-blocked-experiment" / "training_experiment_plan.json").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.training_experiment_plan.v0.1")
        self.assertEqual(payload["status"], "blocked_dataset_not_ready")
        self.assertEqual(payload["reason"], "candidate_store_missing")
        self.assertFalse(payload["runner"]["ready_for_handoff"])
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(manifest_path), payload_text)
        self.assertNotIn("record_json", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertTrue(plan_exists)

    def test_ready_manifest_registers_runner_ready_plan_with_planned_metrics_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "source" / "training_dataset_manifest.json"
            output_root = root / "plans"
            write_manifest(manifest_path, ready_manifest())

            with redirect_stdout(StringIO()) as output:
                exit_code = register_training_experiment.main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--output-root",
                        str(output_root),
                        "--experiment-id",
                        "unit-ready-experiment",
                        "--created-at",
                        "2026-07-05T06:11:00+00:00",
                        "--require-ready",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready_for_runner")
        self.assertTrue(payload["runner"]["ready_for_handoff"])
        self.assertEqual(payload["dataset"]["eligible_records"], 1)
        self.assertEqual(payload["dataset"]["record_sample"][0]["label"], "needs_help")
        self.assertEqual(payload["gates"]["baseline_comparison"], "planned_not_run")
        self.assertEqual(payload["metrics_plan"]["classification"]["accuracy"], "planned_not_measured")
        self.assertEqual(payload["metrics_plan"]["operations"]["energy_per_inference"], "planned_not_measured")
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(manifest_path), payload_text)
        self.assertNotIn("raw_payload", payload_text)

    def test_require_ready_returns_two_for_blocked_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "source" / "training_dataset_manifest.json"
            output_root = root / "plans"
            write_manifest(manifest_path, not_ready_manifest())

            with redirect_stdout(StringIO()) as output:
                exit_code = register_training_experiment.main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--output-root",
                        str(output_root),
                        "--experiment-id",
                        "unit-require-ready-blocked",
                        "--created-at",
                        "2026-07-05T06:12:00+00:00",
                        "--require-ready",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_dataset_not_ready")


if __name__ == "__main__":
    unittest.main()
