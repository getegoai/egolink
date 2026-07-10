from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import run_training_baseline_eval


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def feature_manifest(*, ready: bool = True, row_count: int = 2, synthetic: bool = True) -> dict[str, object]:
    return {
        "schema_version": "egolink.training_feature_manifest.v0.1",
        "builder_version": "train-004.0",
        "feature_set_id": "unit-features",
        "generated_at": "2026-07-06T00:00:00+00:00",
        "status": "ready_for_synthetic_feature_dry_run" if ready and synthetic else (
            "ready_for_feature_runner" if ready else "blocked_feature_rows_mismatch"
        ),
        "reason": "bounded_synthetic_feature_rows_ready_for_runner_dry_run" if ready else "blocked",
        "dataset": {
            "dataset_id": "unit-dataset",
            "status": "ready_for_training_handoff" if ready else "not_ready",
            "eligible_records": row_count if ready else 0,
            "synthetic_records": row_count if synthetic else 0,
        },
        "feature_rows": {
            "row_schema_version": "egolink.training_feature_row.v0.1",
            "row_count": row_count,
            "rows_ref": "training_feature_rows.jsonl",
            "feature_groups": ["imu_motion"],
            "feature_scope": "manifest_summary_features",
            "target_separated_from_features": True,
        },
    }


def runner_dry_run(*, ready: bool = True, synthetic: bool = True, row_count: int = 2) -> dict[str, object]:
    return {
        "schema_version": "egolink.training_runner_dry_run.v0.1",
        "builder_version": "train-005.0",
        "run_id": "unit-runner",
        "created_at": "2026-07-06T00:01:00+00:00",
        "status": "synthetic_runner_dry_run_complete" if ready and synthetic else (
            "ready_for_runner_execution" if ready else "blocked_feature_manifest_not_ready"
        ),
        "feature_rows": {
            "actual_row_count": row_count,
            "expected_row_count": row_count,
            "row_count_matches": True,
            "synthetic_rows": row_count if synthetic else 0,
        },
        "runner": {
            "dry_run_only": synthetic,
        },
        "gates": {
            "runner_input": "pass" if ready else "blocked",
            "model_training": "not_run",
            "model_artifact": "not_produced",
        },
    }


def feature_row(
    *,
    row_id: str,
    split_name: str,
    label: str,
    risk_type: str,
    candidate_type: str,
    synthetic: bool = True,
    leak_label: bool = False,
) -> dict[str, object]:
    features: dict[str, object] = {
        "candidate_type": candidate_type,
        "feature_group_flags": {"has_imu_motion": True},
        "quality_gate_pass": True,
        "source_event_type": "motion_event",
        "source_status": "synthetic_generated" if synthetic else "verified",
    }
    if leak_label:
        features["label"] = label
    return {
        "schema_version": "egolink.training_feature_row.v0.1",
        "feature_set_id": "unit-features",
        "row_id": row_id,
        "record_id": row_id,
        "session_id": f"session-{row_id}",
        "window_id": f"device-001:motion_event:{row_id}:2026-07-06T00:00:00+00:00",
        "split_name": split_name,
        "split_group_key": f"session-{row_id}",
        "target": {
            "label": label,
            "label_review_state": "reviewed",
            "model_labels": {"risk_type": risk_type},
        },
        "source": {
            "candidate_type": candidate_type,
            "feature_groups": ["imu_motion"],
            "source_manifest_hash": f"hash-{row_id}",
            "source_status": "synthetic_generated" if synthetic else "verified",
            "synthetic": synthetic,
        },
        "features": features,
    }


def default_rows(*, synthetic: bool = True) -> list[dict[str, object]]:
    return [
        feature_row(
            row_id="cand-001",
            split_name="train",
            label="safe",
            risk_type="none",
            candidate_type="none",
            synthetic=synthetic,
        ),
        feature_row(
            row_id="cand-002",
            split_name="test",
            label="needs_help",
            risk_type="uncertain",
            candidate_type="uncertain",
            synthetic=synthetic,
        ),
    ]


class TrainingBaselineEvalTests(unittest.TestCase):
    def run_eval(self, args: list[str]) -> tuple[int, dict[str, object]]:
        with redirect_stdout(StringIO()) as output:
            exit_code = run_training_baseline_eval.main(args + ["--json"])
        return exit_code, json.loads(output.getvalue())

    def test_synthetic_rows_require_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            runner_path = root / "inputs" / "training_runner_dry_run.json"
            output_root = root / "eval"
            write_json(manifest_path, feature_manifest(synthetic=True))
            write_jsonl(rows_path, default_rows(synthetic=True))
            write_json(runner_path, runner_dry_run(synthetic=True))

            exit_code, payload = self.run_eval(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--runner-dry-run",
                    str(runner_path),
                    "--output-root",
                    str(output_root),
                    "--eval-id",
                    "unit-synthetic-blocked",
                    "--created-at",
                    "2026-07-06T00:02:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["schema_version"], "egolink.training_baseline_eval.v0.1")
        self.assertEqual(payload["status"], "blocked_synthetic_without_ack")
        self.assertEqual(payload["checks"]["synthetic_row_policy"], "blocked")
        self.assertEqual(payload["gates"]["model_training"], "not_run")

    def test_runner_dry_run_must_be_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            runner_path = root / "inputs" / "training_runner_dry_run.json"
            output_root = root / "eval"
            write_json(manifest_path, feature_manifest(synthetic=True))
            write_jsonl(rows_path, default_rows(synthetic=True))
            write_json(runner_path, runner_dry_run(ready=False, synthetic=True))

            exit_code, payload = self.run_eval(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--runner-dry-run",
                    str(runner_path),
                    "--output-root",
                    str(output_root),
                    "--eval-id",
                    "unit-runner-blocked",
                    "--created-at",
                    "2026-07-06T00:03:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_runner_dry_run_not_ready")
        self.assertFalse(payload["checks"]["runner_dry_run_ready"])

    def test_allow_synthetic_writes_integration_metrics_without_model_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            runner_path = root / "inputs" / "training_runner_dry_run.json"
            output_root = root / "eval"
            write_json(manifest_path, feature_manifest(synthetic=True))
            write_jsonl(rows_path, default_rows(synthetic=True))
            write_json(runner_path, runner_dry_run(synthetic=True))

            exit_code, payload = self.run_eval(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--runner-dry-run",
                    str(runner_path),
                    "--output-root",
                    str(output_root),
                    "--eval-id",
                    "unit-synthetic-ready",
                    "--created-at",
                    "2026-07-06T00:04:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )
            report_exists = (output_root / "unit-synthetic-ready" / "training_baseline_eval.json").exists()
            payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "synthetic_baseline_eval_complete")
        self.assertEqual(payload["metrics"]["scope"], "synthetic_integration_only")
        self.assertTrue(payload["metrics"]["measured_from_rows"])
        baselines = payload["metrics"]["classification"]["baselines"]
        self.assertEqual(baselines[0]["name"], "candidate_type_risk_baseline")
        self.assertEqual(baselines[0]["overall"]["accuracy"], 1.0)
        self.assertEqual(payload["gates"]["model_artifact"], "not_produced")
        self.assertEqual(payload["gates"]["release_claim"], "not_allowed")
        self.assertIn("Synthetic baseline metrics are integration metrics only", " ".join(payload["non_claims"]))
        self.assertTrue(report_exists)
        self.assertNotIn(str(manifest_path), payload_text)
        self.assertNotIn(str(rows_path), payload_text)
        self.assertNotIn("raw_payload", payload_text)

    def test_target_label_leakage_blocks_eval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            runner_path = root / "inputs" / "training_runner_dry_run.json"
            output_root = root / "eval"
            write_json(manifest_path, feature_manifest(synthetic=True, row_count=1))
            write_jsonl(
                rows_path,
                [
                    feature_row(
                        row_id="cand-001",
                        split_name="train",
                        label="needs_help",
                        risk_type="uncertain",
                        candidate_type="uncertain",
                        synthetic=True,
                        leak_label=True,
                    )
                ],
            )
            write_json(runner_path, runner_dry_run(synthetic=True, row_count=1))

            exit_code, payload = self.run_eval(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--runner-dry-run",
                    str(runner_path),
                    "--output-root",
                    str(output_root),
                    "--eval-id",
                    "unit-leakage-blocked",
                    "--created-at",
                    "2026-07-06T00:05:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_target_leakage_guard")
        self.assertEqual(payload["checks"]["target_leakage_violations"], {"features.label": 1})


if __name__ == "__main__":
    unittest.main()
