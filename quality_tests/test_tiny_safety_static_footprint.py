from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from model_lab.safety_companion.evaluation import assess_tiny_safety_static_footprint as footprint


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def fixture_files(root: Path) -> dict[str, Path]:
    artifact = {
        "model_id": "unit-tiny-safety",
        "model_version": "0.1.0-test",
        "model_name": "tiny_safety_model",
        "model_type": "linearized_centroid_classifier",
        "paths": {"synthetic_eval_jsonl": "tmp/eval.jsonl"},
        "linear_model": {
            "feature_names": ["impact", "fall"],
            "state_labels": ["normal", "possible_risk"],
            "weights": [[0.1, 0.2], [0.8, 0.9]],
            "biases": [-0.1, -0.2],
        },
        "test_vectors": [
            {"features": [0.0, 0.1], "expected_label": "normal"},
            {"features": [0.9, 0.8], "expected_label": "possible_risk"},
        ],
    }
    export_report = {
        "deployment": {"firmware_integrated": False, "device_deployed": False},
        "scope": {"hardware_contacted": False, "synthetic_only": True},
    }
    paths = {
        "artifact": write_json(root / "tiny_safety_model.json", artifact),
        "export_report": write_json(root / "export" / "tiny_safety_model_export.json", export_report),
        "test_vectors": write_json(root / "export" / "tiny_safety_test_vectors.json", {"vectors": []}),
        "header": root / "export" / "tiny_safety_model.h",
        "firmware": root / "build" / "egolink_mqtt_heartbeat.bin",
    }
    paths["header"].write_text("static const float weights[] = {0.1f};\n", encoding="utf-8")
    return paths


class TinySafetyStaticFootprintTests(unittest.TestCase):
    def test_static_report_without_firmware_binary_is_l1_and_keeps_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = fixture_files(Path(tmp))
            report = footprint.build_report(
                artifact_path=paths["artifact"],
                export_report_path=paths["export_report"],
                header_path=paths["header"],
                test_vectors_path=paths["test_vectors"],
                firmware_binary_path=paths["firmware"],
                firmware_version="",
                test_run_id="",
                assessed_at="2026-07-07T00:00:00+00:00",
            )

        self.assertEqual(report["evidence_level"], "L1_artifact_estimated")
        self.assertEqual(report["static_model_metrics"]["feature_count"], 2)
        self.assertEqual(report["static_model_metrics"]["class_count"], 2)
        self.assertEqual(report["static_model_metrics"]["parameter_count"], 6)
        self.assertEqual(report["operation_estimate"]["score_multiply_count"], 4)
        self.assertEqual(report["model_footprint_manifest"]["ram_peak_bytes"], "unknown")
        self.assertEqual(report["model_footprint_manifest"]["latency_p95_ms"], "unknown")
        self.assertEqual(report["model_footprint_manifest"]["energy_per_inference_mj"], "unknown")
        self.assertFalse(report["scope"]["prod_001_update_allowed"])
        self.assertIn("Tiny Safety v0 is not MotionNet-class acceptance evidence.", report["known_gaps"])

    def test_existing_firmware_binary_promotes_only_static_partial_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = fixture_files(Path(tmp))
            paths["firmware"].parent.mkdir(parents=True, exist_ok=True)
            paths["firmware"].write_bytes(b"firmware-binary")
            report = footprint.build_report(
                artifact_path=paths["artifact"],
                export_report_path=paths["export_report"],
                header_path=paths["header"],
                test_vectors_path=paths["test_vectors"],
                firmware_binary_path=paths["firmware"],
                firmware_version="0.1.0-test-fw",
                test_run_id="unit-test-run",
                assessed_at="2026-07-07T00:00:00+00:00",
            )

        self.assertEqual(report["evidence_level"], "L2_build_verified_static_partial")
        self.assertEqual(report["model_footprint_manifest"]["flash_total_bytes"], len(b"firmware-binary"))
        self.assertEqual(report["model_footprint_manifest"]["model_static_delta_bytes"], "unknown")
        self.assertEqual(report["firmware_or_benchmark_version"], "0.1.0-test-fw")
        self.assertEqual(report["firmware_test_run_id"], "unit-test-run")
        self.assertFalse(report["scope"]["runtime_measured"])
        self.assertFalse(report["scope"]["power_measured"])

    def test_cli_writes_json_markdown_and_sha_without_hardware_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = fixture_files(root)
            out_dir = root / "assessment"
            exit_code = footprint.main(
                [
                    "--model-artifact",
                    str(paths["artifact"]),
                    "--export-report",
                    str(paths["export_report"]),
                    "--header",
                    str(paths["header"]),
                    "--test-vectors",
                    str(paths["test_vectors"]),
                    "--firmware-binary",
                    str(paths["firmware"]),
                    "--output-dir",
                    str(out_dir),
                    "--assessed-at",
                    "2026-07-07T00:00:00+00:00",
                ]
            )
            report = json.loads((out_dir / footprint.REPORT_JSON).read_text(encoding="utf-8"))
            markdown = (out_dir / footprint.REPORT_MARKDOWN).read_text(encoding="utf-8")
            sha = (out_dir / footprint.SHA256).read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertFalse(report["scope"]["hardware_contacted"])
        self.assertFalse(report["scope"]["firmware_changed"])
        self.assertFalse(report["scope"]["model_training_started"])
        self.assertIn("No runtime RAM, latency, or power measurement is claimed.", markdown)
        self.assertIn(footprint.REPORT_JSON, sha)
        self.assertIn(footprint.REPORT_MARKDOWN, sha)


if __name__ == "__main__":
    unittest.main()
