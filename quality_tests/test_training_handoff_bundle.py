from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_training_handoff_bundle


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_inputs(root: Path, *, synthetic: bool = False, row_count: int = 1) -> dict[str, Path]:
    inputs = root / "inputs"
    dataset_id = "unit-synthetic-dataset" if synthetic else "unit-real-dataset"
    feature_status = "ready_for_synthetic_feature_dry_run" if synthetic else "ready_for_feature_runner"
    runner_status = "synthetic_runner_dry_run_complete" if synthetic else "ready_for_runner_execution"
    baseline_status = "synthetic_baseline_eval_complete" if synthetic else "baseline_eval_complete"
    metric_scope = "synthetic_integration_only" if synthetic else "reviewed_engineering_dataset"
    synthetic_records = row_count if synthetic else 0
    paths = {
        "dataset": inputs / "training_dataset_manifest.json",
        "preflight": inputs / "training_run_preflight.json",
        "feature": inputs / "training_feature_manifest.json",
        "rows": inputs / "training_feature_rows.jsonl",
        "runner": inputs / "training_runner_dry_run.json",
        "baseline": inputs / "training_baseline_eval.json",
    }
    write_json(
        paths["dataset"],
        {
            "schema_version": "egolink.training_dataset_manifest.v0.1",
            "dataset_id": dataset_id,
            "status": "ready_for_training_handoff",
            "counts": {"eligible_records": row_count},
            "split_counts": {"train": row_count},
        },
    )
    write_json(
        paths["preflight"],
        {
            "schema_version": "egolink.training_run_preflight.v0.1",
            "run_id": "unit-preflight",
            "status": "ready_for_training_runner",
            "dataset": {"dataset_id": dataset_id},
            "runner": {"ready_for_training_runner": True},
        },
    )
    write_json(
        paths["feature"],
        {
            "schema_version": "egolink.training_feature_manifest.v0.1",
            "feature_set_id": "unit-features",
            "status": feature_status,
            "dataset": {
                "dataset_id": dataset_id,
                "eligible_records": row_count,
                "synthetic_records": synthetic_records,
            },
            "feature_rows": {
                "row_count": row_count,
                "feature_scope": "manifest_summary_features",
                "target_separated_from_features": True,
            },
        },
    )
    rows = []
    for index in range(row_count):
        rows.append(
            json.dumps(
                {
                    "row_id": f"row-{index}",
                    "record_id": f"record-{index}",
                    "feature_set_id": "unit-features",
                    "target": {"label": "safe", "model_labels": {"risk_type": "none"}},
                    "features": {"candidate_type": "none"},
                    "source": {"synthetic": synthetic},
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    paths["rows"].write_text("\n".join(rows) + "\n", encoding="utf-8")
    write_json(
        paths["runner"],
        {
            "schema_version": "egolink.training_runner_dry_run.v0.1",
            "run_id": "unit-runner",
            "status": runner_status,
            "gates": {"runner_input": "pass"},
        },
    )
    write_json(
        paths["baseline"],
        {
            "schema_version": "egolink.training_baseline_eval.v0.1",
            "eval_id": "unit-eval",
            "status": baseline_status,
            "dataset": {"dataset_id": dataset_id},
            "feature_rows": {
                "actual_row_count": row_count,
                "synthetic_rows": synthetic_records,
            },
            "metrics": {
                "scope": metric_scope,
                "classification": {
                    "product_performance_claim": False,
                    "baselines": [],
                },
            },
        },
    )
    return paths


class TrainingHandoffBundleTests(unittest.TestCase):
    def run_bundle(self, paths: dict[str, Path], output_root: Path, *extra_args: str) -> tuple[int, dict[str, object]]:
        args = [
            "--dataset-manifest",
            str(paths["dataset"]),
            "--preflight",
            str(paths["preflight"]),
            "--feature-manifest",
            str(paths["feature"]),
            "--feature-rows",
            str(paths["rows"]),
            "--runner-dry-run",
            str(paths["runner"]),
            "--baseline-eval",
            str(paths["baseline"]),
            "--output-root",
            str(output_root),
            "--handoff-id",
            "unit-handoff",
            "--created-at",
            "2026-07-06T01:00:00+00:00",
            "--json",
        ]
        with redirect_stdout(StringIO()) as output:
            exit_code = build_training_handoff_bundle.main(args + list(extra_args))
        return exit_code, json.loads(output.getvalue())

    def test_ready_inputs_build_training_server_handoff_without_copying_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = write_inputs(root)
            exit_code, payload = self.run_bundle(paths, root / "handoffs", "--require-ready")
            bundle_path = root / "handoffs" / "unit-handoff" / "training_handoff_bundle.json"
            bundle_exists = bundle_path.is_file()
            payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "egolink.training_handoff_bundle.v0.1")
        self.assertEqual(payload["status"], "ready_for_training_server_handoff")
        self.assertEqual(payload["feature_rows"]["row_count"], 1)
        self.assertFalse(payload["feature_rows"]["content_copied"])
        self.assertFalse(payload["feature_rows"]["raw_rows_exposed"])
        self.assertEqual(payload["training_server"]["integration"], "not_configured")
        self.assertTrue(payload["training_server"]["bundle_ready_for_future_runner"])
        self.assertFalse(payload["baseline_eval"]["product_performance_claim"])
        self.assertEqual(payload["gates"]["model_training"], "not_run")
        self.assertEqual(payload["gates"]["model_artifact"], "not_produced")
        self.assertIn("sha256", payload["source_refs"]["training_feature_rows"])
        self.assertNotIn('"target"', payload_text)
        self.assertNotIn('"features"', payload_text)
        self.assertTrue(bundle_exists)

    def test_synthetic_inputs_require_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = write_inputs(root, synthetic=True)
            exit_code, payload = self.run_bundle(paths, root / "handoffs")
            ack_exit_code, ack_payload = self.run_bundle(paths, root / "handoffs_ack", "--allow-synthetic")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "blocked_synthetic_without_ack")
        self.assertEqual(payload["checks"]["synthetic_policy"], "blocked")
        self.assertEqual(ack_exit_code, 0)
        self.assertEqual(ack_payload["status"], "synthetic_handoff_dry_run_only")
        self.assertTrue(ack_payload["training_server"]["dry_run_only"])
        self.assertEqual(ack_payload["gates"]["training_handoff"], "dry_run_only")

    def test_feature_row_count_mismatch_blocks_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = write_inputs(root, row_count=2)
            paths["rows"].write_text(paths["rows"].read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
            exit_code, payload = self.run_bundle(paths, root / "handoffs")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "blocked_feature_rows_mismatch")
        self.assertFalse(payload["checks"]["feature_row_count_matches"])
        self.assertEqual(payload["feature_rows"]["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
