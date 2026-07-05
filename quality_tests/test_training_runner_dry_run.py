from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import run_training_runner_dry_run


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def feature_manifest(*, ready: bool = True, row_count: int = 1, synthetic: bool = True) -> dict[str, object]:
    return {
        "schema_version": "egolink.training_feature_manifest.v0.1",
        "builder_version": "train-004.0",
        "feature_set_id": "unit-features",
        "generated_at": "2026-07-05T12:00:00+00:00",
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
        "preflight": {
            "run_id": "unit-preflight",
            "status": "ready_for_training_runner" if ready else "blocked",
            "runner_ready": ready,
            "metrics_measured": {
                "classification": "not_run",
                "operations": "not_run",
                "power": "not_run",
            },
        },
        "feature_rows": {
            "row_schema_version": "egolink.training_feature_row.v0.1",
            "row_count": row_count,
            "rows_ref": "training_feature_rows.jsonl",
            "feature_groups": ["imu_motion"],
            "feature_scope": "manifest_summary_features",
            "target_separated_from_features": True,
        },
        "checks": {
            "label_leakage_guard": "target_separated_from_features",
        },
        "gates": {
            "feature_export": "pass" if ready else "blocked",
            "model_training": "not_run",
            "model_artifact": "not_produced",
        },
    }


def feature_row(*, synthetic: bool = True, leak_label: bool = False, feature_set_id: str = "unit-features") -> dict[str, object]:
    features: dict[str, object] = {
        "candidate_type": "uncertain",
        "feature_group_flags": {"has_imu_motion": True},
        "quality_gate_pass": True,
        "source_event_type": "motion_event",
        "source_status": "synthetic_generated" if synthetic else "verified",
    }
    if leak_label:
        features["label"] = "needs_help"
    return {
        "schema_version": "egolink.training_feature_row.v0.1",
        "feature_set_id": feature_set_id,
        "row_id": "cand-001",
        "record_id": "cand-001",
        "session_id": "session-001",
        "window_id": "device-001:motion_event:42:2026-07-05T12:00:00+00:00",
        "split_name": "train",
        "split_group_key": "session-001",
        "target": {
            "label": "needs_help",
            "label_review_state": "reviewed",
            "model_labels": {"risk_type": "uncertain"},
        },
        "source": {
            "candidate_type": "uncertain",
            "feature_groups": ["imu_motion"],
            "source_manifest_hash": "abc123",
            "source_status": "synthetic_generated" if synthetic else "verified",
            "synthetic": synthetic,
        },
        "features": features,
    }


class TrainingRunnerDryRunTests(unittest.TestCase):
    def run_dry_run(self, args: list[str]) -> tuple[int, dict[str, object]]:
        with redirect_stdout(StringIO()) as output:
            exit_code = run_training_runner_dry_run.main(args + ["--json"])
        return exit_code, json.loads(output.getvalue())

    def test_feature_manifest_not_ready_blocks_runner_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            output_root = root / "runner"
            write_json(manifest_path, feature_manifest(ready=False, row_count=0))
            write_jsonl(rows_path, [])

            exit_code, payload = self.run_dry_run(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-manifest-blocked",
                    "--created-at",
                    "2026-07-05T12:30:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["schema_version"], "egolink.training_runner_dry_run.v0.1")
        self.assertEqual(payload["status"], "blocked_feature_manifest_not_ready")
        self.assertEqual(payload["gates"]["model_training"], "not_run")

    def test_synthetic_rows_require_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            output_root = root / "runner"
            write_json(manifest_path, feature_manifest(synthetic=True))
            write_jsonl(rows_path, [feature_row(synthetic=True)])

            exit_code, payload = self.run_dry_run(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-synthetic-blocked",
                    "--created-at",
                    "2026-07-05T12:31:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_synthetic_without_ack")
        self.assertEqual(payload["feature_rows"]["synthetic_rows"], 1)
        self.assertEqual(payload["checks"]["synthetic_row_policy"], "blocked")

    def test_allow_synthetic_completes_runner_input_dry_run_without_model_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            output_root = root / "runner"
            write_json(manifest_path, feature_manifest(synthetic=True))
            write_jsonl(rows_path, [feature_row(synthetic=True)])

            exit_code, payload = self.run_dry_run(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-synthetic-ready",
                    "--created-at",
                    "2026-07-05T12:32:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )
            report_exists = (output_root / "unit-synthetic-ready" / "training_runner_dry_run.json").exists()
            payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "synthetic_runner_dry_run_complete")
        self.assertTrue(payload["runner"]["dry_run_only"])
        self.assertEqual(payload["feature_rows"]["actual_row_count"], 1)
        self.assertEqual(payload["feature_rows"]["label_counts"], {"needs_help": 1})
        self.assertEqual(payload["feature_rows"]["split_counts"], {"train": 1})
        self.assertEqual(payload["checks"]["target_leakage_guard"], "pass")
        self.assertEqual(payload["metrics_plan"]["measured"]["classification"], "not_run")
        self.assertEqual(payload["gates"]["model_artifact"], "not_produced")
        self.assertIn("No model training has run.", payload["non_claims"])
        self.assertNotIn(str(manifest_path), payload_text)
        self.assertNotIn(str(rows_path), payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertTrue(report_exists)

    def test_feature_rows_must_match_manifest_count_and_feature_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            output_root = root / "runner"
            write_json(manifest_path, feature_manifest(row_count=2))
            write_jsonl(rows_path, [feature_row(feature_set_id="wrong-features")])

            exit_code, payload = self.run_dry_run(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-mismatch-blocked",
                    "--created-at",
                    "2026-07-05T12:33:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_feature_rows_mismatch")
        self.assertFalse(payload["feature_rows"]["row_count_matches"])
        self.assertEqual(payload["feature_rows"]["feature_set_mismatch_count"], 1)

    def test_target_label_leakage_blocks_runner_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_feature_manifest.json"
            rows_path = root / "inputs" / "training_feature_rows.jsonl"
            output_root = root / "runner"
            write_json(manifest_path, feature_manifest(synthetic=True))
            write_jsonl(rows_path, [feature_row(synthetic=True, leak_label=True)])

            exit_code, payload = self.run_dry_run(
                [
                    "--feature-manifest",
                    str(manifest_path),
                    "--feature-rows",
                    str(rows_path),
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    "unit-leakage-blocked",
                    "--created-at",
                    "2026-07-05T12:34:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_target_leakage_guard")
        self.assertEqual(payload["checks"]["target_leakage_violations"], {"features.label": 1})


if __name__ == "__main__":
    unittest.main()
