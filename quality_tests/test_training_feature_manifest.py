from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts import export_training_feature_manifest


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dataset_manifest(*, synthetic: bool = False, incomplete: bool = False) -> dict[str, object]:
    record = {
        "record_id": "cand-001",
        "session_id": "session-001",
        "window_id": "device-001:motion_event:42:2026-07-05T12:00:00+00:00",
        "candidate_type": "uncertain",
        "device_id": "device-001",
        "feature_generator_version": "not_generated",
        "feature_groups": ["imu_motion"],
        "firmware_version": "data-009.0",
        "label": "needs_help",
        "label_review_state": "reviewed",
        "model_labels": {
            "action_outcome": "help_requested",
            "risk_type": "uncertain",
            "severity": "high",
            "user_state": "needs_help",
        },
        "privacy_class": "structured_sensor_event",
        "quality_gate": "pass",
        "quality_score": 0.95,
        "source_event_type": "motion_event",
        "source_manifest_hash": "abc123",
        "source_status": "synthetic_generated" if synthetic else "verified",
        "split_group_key": "session-001",
        "split_name": "train",
    }
    if incomplete:
        record.pop("source_manifest_hash")
    return {
        "schema_version": "egolink.training_dataset_manifest.v0.1",
        "builder_version": "train-001.0",
        "dataset_id": "unit-ready-dataset",
        "generated_at": "2026-07-05T12:00:00+00:00",
        "status": "ready_for_training_handoff",
        "reason": "reviewed_candidates_available",
        "counts": {
            "records_total": 1,
            "eligible_records": 1,
            "reviewed_training_candidate_records": 1,
        },
        "split_counts": {"train": 1},
        "records": [record],
    }


def preflight_report(*, ready: bool = True, dataset_id: str = "unit-ready-dataset") -> dict[str, object]:
    return {
        "schema_version": "egolink.training_run_preflight.v0.1",
        "builder_version": "train-003.0",
        "run_id": "unit-preflight",
        "created_at": "2026-07-05T12:05:00+00:00",
        "status": "ready_for_training_runner" if ready else "blocked_dataset_not_ready",
        "reason": "bounded_dataset_and_experiment_handoff_ready" if ready else "dataset_not_ready",
        "dataset": {
            "dataset_id": dataset_id,
            "status": "ready_for_training_handoff" if ready else "not_ready",
            "eligible_records": 1 if ready else 0,
            "synthetic_records": 1,
            "split_counts": {"train": 1} if ready else {},
        },
        "runner": {
            "integration": "local_preflight_only",
            "ready_for_training_runner": ready,
            "training_server_endpoint": None,
        },
        "metrics_plan": {
            "measured": {
                "classification": "not_run",
                "operations": "not_run",
                "footprint": "not_run",
                "power": "not_run",
            }
        },
        "gates": {
            "preflight_ready": ready,
            "model_training": "not_run",
            "model_evaluation": "not_run",
            "model_artifact": "not_produced",
        },
    }


class TrainingFeatureManifestTests(unittest.TestCase):
    def run_export(self, args: list[str]) -> tuple[int, dict[str, object]]:
        with redirect_stdout(StringIO()) as output:
            exit_code = export_training_feature_manifest.main(args + ["--json"])
        return exit_code, json.loads(output.getvalue())

    def test_preflight_not_ready_blocks_feature_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            preflight_path = root / "inputs" / "training_run_preflight.json"
            output_root = root / "features"
            write_json(manifest_path, dataset_manifest())
            write_json(preflight_path, preflight_report(ready=False))

            exit_code, payload = self.run_export(
                [
                    "--dataset-manifest",
                    str(manifest_path),
                    "--preflight",
                    str(preflight_path),
                    "--output-root",
                    str(output_root),
                    "--feature-set-id",
                    "unit-preflight-blocked",
                    "--generated-at",
                    "2026-07-05T12:10:00+00:00",
                    "--require-ready",
                ]
            )
            payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["schema_version"], "egolink.training_feature_manifest.v0.1")
        self.assertEqual(payload["status"], "blocked_preflight_not_ready")
        self.assertEqual(payload["feature_rows"]["row_count"], 0)
        self.assertEqual(payload["gates"]["model_training"], "not_run")
        self.assertNotIn(str(manifest_path), payload_text)
        self.assertNotIn(str(preflight_path), payload_text)
        self.assertNotIn("recording_path", payload_text)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn("candidate.db", payload_text)

    def test_synthetic_records_require_explicit_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            preflight_path = root / "inputs" / "training_run_preflight.json"
            output_root = root / "features"
            write_json(manifest_path, dataset_manifest(synthetic=True))
            write_json(preflight_path, preflight_report())

            exit_code, payload = self.run_export(
                [
                    "--dataset-manifest",
                    str(manifest_path),
                    "--preflight",
                    str(preflight_path),
                    "--output-root",
                    str(output_root),
                    "--feature-set-id",
                    "unit-synthetic-blocked",
                    "--generated-at",
                    "2026-07-05T12:11:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_synthetic_without_ack")
        self.assertEqual(payload["dataset"]["synthetic_records"], 1)
        self.assertEqual(payload["checks"]["synthetic_record_policy"], "blocked")
        self.assertEqual(payload["feature_rows"]["row_count"], 0)

    def test_allow_synthetic_exports_bounded_feature_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            preflight_path = root / "inputs" / "training_run_preflight.json"
            output_root = root / "features"
            write_json(manifest_path, dataset_manifest(synthetic=True))
            write_json(preflight_path, preflight_report())

            exit_code, payload = self.run_export(
                [
                    "--dataset-manifest",
                    str(manifest_path),
                    "--preflight",
                    str(preflight_path),
                    "--output-root",
                    str(output_root),
                    "--feature-set-id",
                    "unit-synthetic-ready",
                    "--generated-at",
                    "2026-07-05T12:12:00+00:00",
                    "--allow-synthetic",
                    "--require-ready",
                ]
            )
            rows_path = output_root / "unit-synthetic-ready" / "training_feature_rows.jsonl"
            rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            row_text = json.dumps(rows, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ready_for_synthetic_feature_dry_run")
        self.assertEqual(payload["feature_rows"]["row_count"], 1)
        self.assertEqual(payload["checks"]["label_leakage_guard"], "target_separated_from_features")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"]["label"], "needs_help")
        self.assertTrue(rows[0]["source"]["synthetic"])
        self.assertTrue(rows[0]["features"]["feature_group_flags"]["has_imu_motion"])
        self.assertEqual(rows[0]["features"]["firmware_family"], "data-009")
        self.assertNotIn("label", rows[0]["features"])
        self.assertNotIn("model_labels", rows[0]["features"])
        self.assertNotIn("recording_path", row_text)
        self.assertNotIn("raw_payload", row_text)

    def test_incomplete_record_blocks_feature_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "inputs" / "training_dataset_manifest.json"
            preflight_path = root / "inputs" / "training_run_preflight.json"
            output_root = root / "features"
            write_json(manifest_path, dataset_manifest(incomplete=True))
            write_json(preflight_path, preflight_report())

            exit_code, payload = self.run_export(
                [
                    "--dataset-manifest",
                    str(manifest_path),
                    "--preflight",
                    str(preflight_path),
                    "--output-root",
                    str(output_root),
                    "--feature-set-id",
                    "unit-incomplete-blocked",
                    "--generated-at",
                    "2026-07-05T12:13:00+00:00",
                    "--require-ready",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked_incomplete_records")
        self.assertEqual(payload["checks"]["missing_record_fields"], {"source_manifest_hash": 1})
        self.assertEqual(payload["feature_rows"]["row_count"], 0)


if __name__ == "__main__":
    unittest.main()
