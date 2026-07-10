from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from model_lab.safety_companion.export import export_tiny_safety_model
from model_lab.safety_companion.src import tiny_safety_model
from model_lab.safety_companion.training import train_tiny_safety_model


def model_input(
    *,
    impact: float = 0.0,
    fall: float = 0.0,
    stationary_seconds: float = 0.0,
    distress: float = 0.0,
    impact_sound: float = 0.0,
    unknown_loud: float = 0.0,
    sos: bool = False,
    cancel: bool = False,
) -> dict[str, object]:
    return {
        "contract_version": "1.0.0",
        "input_id": "unit-input",
        "device_id": "ego-link-unit",
        "timestamp_ms": 1,
        "mode": "test",
        "features": {
            "motion": {
                "activity_label": "unknown",
                "activity_confidence": 0.8,
                "impact_score": impact,
                "fall_score": fall,
                "stationary_seconds": stationary_seconds,
                "device_worn": True,
            },
            "audio": {
                "speech_score": 0.0,
                "distress_score": distress,
                "impact_sound_score": impact_sound,
                "unknown_loud_sound_score": unknown_loud,
                "quality_score": 1.0,
            },
            "location": {
                "fix_valid": True,
                "speed_mps": 0.0,
                "outside_safe_zone": False,
                "dwell_seconds": 0.0,
                "route_deviation_m": 0.0,
                "quality_score": 0.8,
            },
            "network": {
                "connectivity_score": 0.8,
                "base_online": True,
                "upload_available": True,
                "signal_level": 4,
                "offline_seconds": 0.0,
            },
            "device": {
                "battery_percent": 86.0,
                "charging": False,
                "privacy_mode": False,
                "camera_available": False,
                "microphone_available": False,
            },
            "history": {
                "recent_risk_count_5m": 0,
                "last_user_response": "none",
                "seconds_since_last_contact": 0.0,
            },
            "user": {"sos_pressed": sos, "cancel_pressed": cancel},
        },
        "evidence_available": {
            "audio_clip": False,
            "single_image": False,
            "fresh_gnss": True,
            "imu_window": True,
        },
        "metadata": {"unit": True},
    }


class TinySafetyModelTests(unittest.TestCase):
    def build_artifact(self) -> dict[str, object]:
        rows = tiny_safety_model.synthetic_training_rows(samples_per_class=12, seed=11)
        training_rows, holdout_rows = tiny_safety_model.split_rows(rows)
        return tiny_safety_model.build_artifact(
            model_id="unit-tiny-safety",
            generated_at="2026-07-07T00:00:00+00:00",
            training_rows=training_rows,
            holdout_rows=holdout_rows,
        )

    def test_tiny_model_predicts_four_states_without_user_override_control(self) -> None:
        artifact = self.build_artifact()

        normal = tiny_safety_model.predict(model_input(), artifact)
        uncertain = tiny_safety_model.predict(model_input(impact=0.3, fall=0.2, unknown_loud=0.5), artifact)
        needs_check = tiny_safety_model.predict(
            model_input(impact=0.55, fall=0.62, stationary_seconds=35, impact_sound=0.42),
            artifact,
        )
        risk = tiny_safety_model.predict(
            model_input(impact=0.9, fall=0.82, stationary_seconds=95, distress=0.6, impact_sound=0.72),
            artifact,
        )
        sos = tiny_safety_model.predict(model_input(sos=True), artifact)
        cancel = tiny_safety_model.predict(model_input(cancel=True), artifact)

        self.assertEqual(normal.state_label, "normal")
        self.assertEqual(uncertain.state_label, "uncertain")
        self.assertEqual(needs_check.state_label, "needs_check")
        self.assertEqual(risk.state_label, "possible_risk")
        self.assertTrue(sos.safety_rule_required)
        self.assertTrue(cancel.safety_rule_required)
        self.assertEqual(sos.state_label, "safety_rule_required")
        self.assertNotIn("sos", " ".join(tiny_safety_model.FEATURE_NAMES))
        self.assertNotIn("cancel", " ".join(tiny_safety_model.FEATURE_NAMES))

    def test_training_script_writes_synthetic_artifact_without_deployment_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = train_tiny_safety_model.main(
                    [
                        "--model-id",
                        "unit-train-model",
                        "--generated-at",
                        "2026-07-07T00:00:00+00:00",
                        "--output-root",
                        str(root),
                        "--samples-per-class",
                        "12",
                        "--json",
                    ]
                )
            artifact = json.loads(stdout.getvalue())
            output_dir = root / "unit-train-model"
            artifact_text = (output_dir / "tiny_safety_model.json").read_text(encoding="utf-8")
            card_text = (output_dir / "tiny_safety_model_card.md").read_text(encoding="utf-8")
            eval_text = (output_dir / "tiny_safety_eval.jsonl").read_text(encoding="utf-8")
            sha_text = (output_dir / "sha256.txt").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(artifact["schema_version"], "egolink.tiny_safety_model.v0.1")
        self.assertEqual(artifact["output_state_labels"], list(tiny_safety_model.STATE_LABELS))
        self.assertTrue(artifact["training_data"]["synthetic_only"])
        self.assertEqual(artifact["training_data"]["real_field_rows"], 0)
        self.assertEqual(artifact["training_data"]["private_rows"], 0)
        self.assertEqual(artifact["metrics"]["metric_scope"], "synthetic_integration_only")
        self.assertFalse(artifact["deployment"]["firmware_integrated"])
        self.assertFalse(artifact["deployment"]["device_deployed"])
        self.assertIsNone(artifact["deployment"]["measured_power_mw"])
        self.assertTrue(artifact["safety"]["sos_cancel_handled_by_safety_kernel"])
        self.assertFalse(artifact["safety"]["model_controls_external_actions"])
        self.assertFalse(artifact["safety"]["release_claim_allowed"])
        self.assertIn("Synthetic integration model only", artifact_text + card_text)
        self.assertIn('"synthetic_only": true', eval_text)
        self.assertIn("tiny_safety_model.json", sha_text)
        self.assertIn("tiny_safety_eval.jsonl", sha_text)
        self.assertNotIn("production", artifact_text.lower())
        self.assertNotIn("release ready", card_text.lower())

    def test_export_script_writes_c_header_and_test_vectors_without_firmware_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train_tiny_safety_model.main(
                [
                    "--model-id",
                    "unit-export-model",
                    "--generated-at",
                    "2026-07-07T00:00:00+00:00",
                    "--output-root",
                    str(root),
                    "--samples-per-class",
                    "12",
                ]
            )
            artifact_path = root / "unit-export-model" / "tiny_safety_model.json"
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = export_tiny_safety_model.main(
                    [
                        "--model-artifact",
                        str(artifact_path),
                        "--output-dir",
                        str(root / "export"),
                        "--exported-at",
                        "2026-07-07T00:10:00+00:00",
                        "--json",
                    ]
                )
            report = json.loads(stdout.getvalue())
            header_text = (root / "export" / "tiny_safety_model.h").read_text(encoding="utf-8")
            vector_payload = json.loads((root / "export" / "tiny_safety_test_vectors.json").read_text(encoding="utf-8"))
            sha_text = (root / "export" / "sha256.txt").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertFalse(report["deployment"]["firmware_integrated"])
        self.assertFalse(report["deployment"]["device_deployed"])
        self.assertFalse(report["scope"]["hardware_contacted"])
        self.assertFalse(report["scope"]["firmware_changed"])
        self.assertIn("#define EGO_TINY_SAFETY_FEATURE_COUNT", header_text)
        self.assertIn("ego_tiny_safety_weights", header_text)
        self.assertIn("ego_tiny_safety_test_expected", header_text)
        self.assertIn("tiny_safety_model.h", sha_text)
        self.assertTrue(vector_payload["synthetic_only"])
        self.assertEqual(len(vector_payload["state_labels"]), 4)
        self.assertNotIn("measured_power_mw = 0", header_text)


if __name__ == "__main__":
    unittest.main()
