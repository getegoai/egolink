from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from pc_simulator.tinyml_ego_state_model import TinyMLEgoStateModel, INPUT_LENGTH, INPUT_CHANNELS
from pc_simulator.safety_kernel_arbitrator import SafetyKernelArbitrator
from scripts.train_edge_tinyml_model import generate_synthetic_dataset, train_tinyml_model
from scripts.finetune_flywheel_model import (
    load_gold_samples,
    blend_with_anchor_replay_buffer,
    run_safety_regression_gate,
    package_model_binary,
    verify_model_binary,
    finetune_flywheel_model,
    SafetyRegressionError,
    BINARY_MAGIC,
)


class TestFinetuneFlywheelPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Baseline model initialized and trained
        X, y = generate_synthetic_dataset(samples_per_class=15, seed=42)
        cls.base_model = TinyMLEgoStateModel(seed=42)
        train_tinyml_model(cls.base_model, X, y, epochs=40, learning_rate=0.015)

    def _create_dummy_gold_samples_file(self, file_path: Path) -> None:
        """Create sample mined_gold_samples.jsonl for tests."""
        rng = np.random.default_rng(42)
        samples = []
        for i in range(12):
            t = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
            t[:, 2] = 9.81 + 8.0 * np.sin(np.linspace(0, 15, INPUT_LENGTH))
            samples.append({
                "window_id": f"gold-sample-{i:03d}",
                "raw_tensor": t.tolist(),
                "arbitrated_state": "running",
                "tinyml_state": "running",
                "conflict_description": "TinyML predicts 'running' but GNSS ground speed is 0.0 m/s",
                "evidence_digest": f"digest-{i}",
            })
        with open(file_path, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")

    def test_gold_samples_loading_and_blending(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            gold_file = Path(tmp_dir) / "test_gold.jsonl"
            self._create_dummy_gold_samples_file(gold_file)

            X_gold, y_gold, meta = load_gold_samples(gold_file)
            self.assertEqual(X_gold.shape, (12, 100, 6))
            self.assertEqual(len(y_gold), 12)
            self.assertEqual(len(meta), 12)

            X_blend, y_blend = blend_with_anchor_replay_buffer(X_gold, y_gold, anchors_per_class=10, seed=42)
            # 12 gold + 6 classes * 10 anchors = 72 samples
            self.assertEqual(len(y_blend), 12 + 60)
            self.assertEqual(X_blend.shape, (72, 100, 6))

    def test_safety_regression_gate_passes_healthy_model(self):
        arbitrator = SafetyKernelArbitrator(self.base_model)
        res = run_safety_regression_gate(self.base_model, arbitrator)
        self.assertEqual(res["gate_status"], "PASSED")
        self.assertEqual(res["recall"], 1.0)
        self.assertGreaterEqual(res["passed_vectors"], 15)

    def test_safety_regression_gate_aborts_on_failure(self):
        # Create a flawed arbitrator that suppresses fall alerts
        class FlawedArbitrator(SafetyKernelArbitrator):
            def arbitrate_window(self, raw_tensor, device_context=None, window_id="win"):
                res = super().arbitrate_window(raw_tensor, device_context, window_id=window_id)
                # Intentionally downgrade fall to stationary
                if res["arbitrated_state"] == "fall_suspected":
                    res["arbitrated_state"] = "stationary"
                    res["is_safety_override"] = False
                return res

        flawed_arb = FlawedArbitrator(self.base_model)
        with self.assertRaises(SafetyRegressionError):
            run_safety_regression_gate(self.base_model, flawed_arb)

    def test_model_binary_packaging_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bin_path = Path(tmp_dir) / "ego_model_v2.bin"
            pkg_info = package_model_binary(self.base_model, bin_path, model_version=2)

            self.assertTrue(bin_path.is_file())
            self.assertGreater(pkg_info["binary_size_bytes"], 5000)
            self.assertLess(pkg_info["binary_size_bytes"], 10000)  # ~5.7 KB
            self.assertEqual(pkg_info["model_version"], 2)

            # Verification
            verify_res = verify_model_binary(bin_path)
            self.assertTrue(verify_res["is_valid"])
            self.assertEqual(verify_res["model_version"], 2)
            self.assertEqual(verify_res["num_classes"], 6)
            self.assertEqual(verify_res["total_parameters"], 5622)
            self.assertEqual(verify_res["sha256_hex"], pkg_info["sha256_hex"])

            # Tampering test: flip one byte in the binary
            raw_bytes = bytearray(bin_path.read_bytes())
            raw_bytes[100] ^= 0xFF
            tampered_bin = Path(tmp_dir) / "tampered.bin"
            tampered_bin.write_bytes(raw_bytes)

            with self.assertRaises(ValueError) as ctx:
                verify_model_binary(tampered_bin)
            self.assertIn("Checksum mismatch", str(ctx.exception))

    def test_end_to_end_flywheel_finetune_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            gold_file = Path(tmp_dir) / "gold_samples.jsonl"
            self._create_dummy_gold_samples_file(gold_file)
            out_dir = Path(tmp_dir) / "output_v2"

            report = finetune_flywheel_model(
                self.base_model,
                gold_file,
                out_dir,
                model_version=2,
                epochs=30,
                learning_rate=0.01,
            )

            self.assertEqual(report["model_version"], 2)
            self.assertEqual(report["safety_regression_gate"]["gate_status"], "PASSED")
            self.assertTrue(report["verification"]["is_valid"])

            # Check files created
            self.assertTrue((out_dir / "ego_model_v2.bin").is_file())
            self.assertTrue((out_dir / "tinyml_ego_state_weights_v2.h").is_file())
            self.assertTrue((out_dir / "retraining_report.json").is_file())
            self.assertTrue((out_dir / "retraining_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
