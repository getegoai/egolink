from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from pc_simulator.tinyml_ego_state_model import TinyMLEgoStateModel, INPUT_LENGTH, INPUT_CHANNELS
from pc_simulator.safety_kernel_arbitrator import SafetyKernelArbitrator
from scripts.train_edge_tinyml_model import generate_synthetic_dataset, train_tinyml_model
from scripts.run_shadow_evaluation import create_scenario_benchmark_dataset, run_shadow_evaluation


class TestSafetyKernelShadowEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize and train a baseline model so heads are calibrated
        X, y = generate_synthetic_dataset(samples_per_class=20, seed=42)
        cls.model = TinyMLEgoStateModel(seed=42)
        train_tinyml_model(cls.model, X, y, epochs=50, learning_rate=0.015)
        cls.arbitrator = SafetyKernelArbitrator(cls.model)

    def test_sos_button_safety_override(self):
        """Physical SOS button must have unconditional veto authority over AI inference."""
        # Clean stationary signal
        dummy_tensor = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        dummy_tensor[:, 2] = 9.81
        context = {"sos_button_pressed": True, "battery_percent": 85.0}

        res = self.arbitrator.arbitrate_window(dummy_tensor.tolist(), context, window_id="win-sos-01")

        self.assertTrue(res["is_safety_override"])
        self.assertEqual(res["arbitrated_state"], "manual_sos")
        self.assertEqual(res["arbitrated_priority"], "critical")
        self.assertEqual(res["decision_source"], "safety_kernel_override")
        # AI inference is recorded in shadow telemetry but overridden
        self.assertIn("tinyml_inference", res)
        self.assertIn("class_name", res["tinyml_inference"])

    def test_fall_detection_safety_override(self):
        """Impact spike followed by silence must trigger critical fall alert."""
        tensor = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        tensor[:, 2] = 9.81
        tensor[20:25, 2] = 32.0  # Deceleration spike > 30 m/s^2
        tensor[25:, 2] = 9.81   # Immobility

        context = {"sos_button_pressed": False, "gnss_speed_mps": 0.0}
        res = self.arbitrator.arbitrate_window(tensor.tolist(), context, window_id="win-fall-01")

        self.assertTrue(res["is_safety_override"])
        self.assertEqual(res["arbitrated_state"], "fall_suspected")
        self.assertEqual(res["arbitrated_priority"], "critical")
        self.assertEqual(res["decision_source"], "safety_kernel_override")

    def test_battery_critical_cutoff_override(self):
        """Emergency battery cutoff must trigger safety override."""
        tensor = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        tensor[:, 2] = 9.81
        context = {"battery_critical_cutoff": True, "battery_percent": 1.0}

        res = self.arbitrator.arbitrate_window(tensor.tolist(), context, window_id="win-pwr-01")

        self.assertTrue(res["is_safety_override"])
        self.assertEqual(res["arbitrated_state"], "critical_power_cutoff")
        self.assertEqual(res["arbitrated_priority"], "critical")

    def test_normal_tinyml_enrichment_without_override(self):
        """In normal regime without safety triggers, confident TinyML enriches state."""
        rng = np.random.default_rng(42)
        t = np.linspace(0, 5.0, INPUT_LENGTH)
        tensor = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        tensor[:, 2] = 9.81 + 3.0 * np.sin(2 * np.pi * 1.6 * t) + rng.normal(0, 0.2, INPUT_LENGTH)
        tensor[:, 0] = 1.5 * np.cos(2 * np.pi * 1.6 * t) + rng.normal(0, 0.1, INPUT_LENGTH)
        tensor[:, 4] = 40.0 * np.sin(2 * np.pi * 1.6 * t) + rng.normal(0, 2.0, INPUT_LENGTH)

        context = {"gnss_speed_mps": 1.4, "gnss_fix_type": "3D", "is_charging": False}
        res = self.arbitrator.arbitrate_window(tensor.tolist(), context, window_id="win-walk-01")

        self.assertFalse(res["is_safety_override"])
        self.assertEqual(res["arbitrated_state"], "walking")
        self.assertEqual(res["decision_source"], "tinyml_edge_model")
        self.assertGreaterEqual(res["tinyml_inference"]["confidence"], 0.65)
        self.assertLess(res["tinyml_inference"]["entropy"], 1.20)

    def test_sensor_conflict_and_gold_sample_mining(self):
        """Cross-modal conflict (running IMU with 0 m/s GNSS) flags a Gold Sample."""
        rng = np.random.default_rng(42)
        t = np.linspace(0, 5.0, INPUT_LENGTH)
        tensor = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        tensor[:, 2] = 9.81 + 8.5 * np.sin(2 * np.pi * 3.0 * t) + rng.normal(0, 0.5, INPUT_LENGTH)
        tensor[:, 0] = 4.0 * np.cos(2 * np.pi * 3.0 * t) + rng.normal(0, 0.3, INPUT_LENGTH)
        tensor[:, 4] = 90.0 * np.sin(2 * np.pi * 3.0 * t) + rng.normal(0, 5.0, INPUT_LENGTH)

        # GNSS says 0 m/s ground speed with 3D fix
        context = {"gnss_speed_mps": 0.0, "gnss_fix_type": "3D", "gnss_hdop": 0.8}
        res = self.arbitrator.arbitrate_window(tensor.tolist(), context, window_id="win-treadmill-01")

        self.assertTrue(res["sensor_conflict_flag"])
        self.assertTrue(res["is_gold_sample_for_flywheel"])
        self.assertIn("GNSS ground speed is 0.0 m/s", res["conflict_description"])

    def test_run_shadow_evaluation_end_to_end(self):
        """Test full shadow evaluation pipeline, artifact exports, and metrics."""
        windows = create_scenario_benchmark_dataset()
        self.assertGreater(len(windows), 30)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "shadow_v1"
            summary = run_shadow_evaluation(self.arbitrator, windows, out_dir)

            self.assertEqual(summary["total_windows_evaluated"], len(windows))
            # 3 SOS + 3 Falls = 6 safety overrides
            self.assertEqual(summary["safety_overrides_triggered"], 6)
            # Gold samples mined from treadmill / conflicts
            self.assertGreater(summary["gold_samples_mined"], 0)

            # Check exported files
            summary_file = out_dir / "shadow_evaluation_summary.json"
            report_file = out_dir / "shadow_evaluation_report.md"
            gold_file = out_dir / "mined_gold_samples.jsonl"

            self.assertTrue(summary_file.is_file())
            self.assertTrue(report_file.is_file())
            self.assertTrue(gold_file.is_file())

            report_text = report_file.read_text(encoding="utf-8")
            self.assertIn("Dual-Track Shadow Evaluation", report_text)
            self.assertIn("Safety Kernel Priority Verification", report_text)

            gold_lines = gold_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(gold_lines), summary["gold_samples_mined"])


if __name__ == "__main__":
    unittest.main()
