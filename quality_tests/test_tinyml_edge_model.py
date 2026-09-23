from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from pc_simulator.tinyml_ego_state_model import (
    CLASS_NAMES,
    NUM_CLASSES,
    INPUT_LENGTH,
    INPUT_CHANNELS,
    TinyMLEgoStateModel,
    calculate_entropy,
    softmax,
)
from scripts.train_edge_tinyml_model import (
    normalize_imu_tensor,
    load_dataset_from_jsonl,
    generate_synthetic_dataset,
    train_tinyml_model,
    evaluate_model,
)


class TestTinyMLEdgeModel(unittest.TestCase):
    def test_model_instantiation_and_footprint(self):
        model = TinyMLEgoStateModel(seed=42)
        meta = model.get_parameter_count()

        # Total parameter count should be ~5622
        self.assertGreater(meta["total_parameters"], 5000)
        self.assertLess(meta["total_parameters"], 7000)

        # INT8 footprint must be well under the 30 KB budget
        self.assertTrue(meta["fits_in_sram_under_30kb"])
        self.assertLess(meta["int8_footprint_kb"], 10.0)  # ~5.5 KB
        self.assertLess(meta["float32_footprint_kb"], 30.0)

    def test_forward_pass_shapes(self):
        model = TinyMLEgoStateModel(seed=42)

        # Single tensor [100, 6]
        x_single = np.random.randn(INPUT_LENGTH, INPUT_CHANNELS).astype(np.float32)
        probs, logits = model.forward(x_single)
        self.assertEqual(probs.shape, (NUM_CLASSES,))
        self.assertEqual(logits.shape, (NUM_CLASSES,))
        self.assertAlmostEqual(float(np.sum(probs)), 1.0, places=5)

        # Batch input [3, 100, 6]
        x_batch = np.random.randn(3, INPUT_LENGTH, INPUT_CHANNELS).astype(np.float32)
        probs_b, logits_b = model.forward(x_batch)
        self.assertEqual(probs_b.shape, (3, NUM_CLASSES))
        self.assertEqual(logits_b.shape, (3, NUM_CLASSES))
        for i in range(3):
            self.assertAlmostEqual(float(np.sum(probs_b[i])), 1.0, places=5)

    def test_predict_and_entropy(self):
        model = TinyMLEgoStateModel(seed=42)
        x = np.random.randn(INPUT_LENGTH, INPUT_CHANNELS).astype(np.float32)
        pred = model.predict(x)

        self.assertIn("class_index", pred)
        self.assertIn(pred["class_name"], CLASS_NAMES)
        self.assertGreaterEqual(pred["confidence"], 0.0)
        self.assertLessEqual(pred["confidence"], 1.0)
        self.assertGreaterEqual(pred["entropy"], 0.0)
        self.assertEqual(len(pred["probabilities"]), NUM_CLASSES)

        # Theoretical uniform entropy check: -sum(1/6 * log2(1/6)) = log2(6) ~ 2.58496
        uniform_p = np.full(NUM_CLASSES, 1.0 / NUM_CLASSES)
        self.assertAlmostEqual(calculate_entropy(uniform_p), 2.58496, places=4)

    def test_int8_quantization_and_c_header_export(self):
        model = TinyMLEgoStateModel(seed=42)
        q = model.quantize_int8()

        # Check all layers quantized into int8
        self.assertIn("conv1_w", q)
        for name, data in q.items():
            vals = np.array(data["int8_values"])
            self.assertTrue(np.all(vals >= -128))
            self.assertTrue(np.all(vals <= 127))
            self.assertGreater(data["scale"], 0.0)

        # Export C header
        with tempfile.TemporaryDirectory() as tmp_dir:
            header_path = Path(tmp_dir) / "tinyml_ego_state_weights.h"
            model.export_c_header(header_path)
            self.assertTrue(header_path.is_file())

            content = header_path.read_text(encoding="utf-8")
            self.assertIn("#pragma once", content)
            self.assertIn("#define TINYML_INPUT_LENGTH 100", content)
            self.assertIn("static const int8_t conv1_w_weights[", content)
            self.assertIn("static const float conv1_w_scale =", content)

    def test_synthetic_training_and_evaluation(self):
        # Generate small dataset
        X, y = generate_synthetic_dataset(samples_per_class=15, seed=42)
        self.assertEqual(X.shape[0], 15 * NUM_CLASSES)
        self.assertEqual(X.shape[1:], (INPUT_LENGTH, INPUT_CHANNELS))

        model = TinyMLEgoStateModel(seed=42)
        pre_eval = evaluate_model(model, X, y)
        self.assertEqual(pre_eval["num_samples"], 15 * NUM_CLASSES)
        self.assertEqual(len(pre_eval["confusion_matrix"]), NUM_CLASSES)

        # Train for 50 epochs with Adam
        train_res = train_tinyml_model(model, X, y, epochs=50, learning_rate=0.015, batch_size=16)
        self.assertEqual(train_res["epochs"], 50)
        # Loss should decrease from initial to final
        self.assertLess(train_res["final_loss"], train_res["loss_history"][0])

        # Post training evaluation
        post_eval = evaluate_model(model, X, y)
        self.assertGreaterEqual(post_eval["accuracy"], 0.70)
        for cname in CLASS_NAMES:
            self.assertIn(cname, post_eval["class_metrics"])
            self.assertEqual(post_eval["class_metrics"][cname]["support"], 15)

    def test_load_dataset_from_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            jsonl_path = Path(tmp_dir) / "test_windows.jsonl"
            dummy_tensor = [[0.0, 0.0, 9.81, 0.0, 0.0, 0.0]] * 100

            record1 = {
                "window_id": "win-001",
                "raw_tensor": dummy_tensor,
                "pseudo_label": {"class_name": "walking", "confidence": 0.9},
            }
            record2 = {
                "window_id": "win-002",
                "raw_tensor": dummy_tensor,
                "pseudo_label": {"class_name": "stationary", "confidence": 0.95},
            }

            with open(jsonl_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(record1) + "\n")
                f.write(json.dumps(record2) + "\n")

            X, y, meta = load_dataset_from_jsonl(jsonl_path)
            self.assertEqual(X.shape, (2, 100, 6))
            self.assertEqual(y[0], 1)  # walking -> 1
            self.assertEqual(y[1], 0)  # stationary -> 0
            self.assertEqual(len(meta), 2)


if __name__ == "__main__":
    unittest.main()
