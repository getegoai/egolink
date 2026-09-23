"""Train and evaluate the TinyML 1D-CNN Ego-State edge model (AI-020).

This script:
1. Loads pseudo-labeled window records from `windows.jsonl` (produced by
   `harvest_self_supervised_dataset.py`).
2. Preprocesses and normalizes 6-axis IMU tensors [100, 6].
3. Trains the TinyML 1D-CNN using mini-batch gradient descent.
4. Evaluates classification accuracy, per-class F1-scores, and confusion matrix.
5. Exports the trained model weights to JSON and C header for ESP32-S3 deployment.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pc_simulator.tinyml_ego_state_model import (
    CLASS_NAMES,
    NUM_CLASSES,
    INPUT_LENGTH,
    INPUT_CHANNELS,
    TinyMLEgoStateModel,
    softmax,
    relu,
    calculate_entropy,
)


LABEL_MAP: Dict[str, int] = {
    "stationary": 0,
    "stationary_charging": 0,
    "walking": 1,
    "running": 2,
    "cycling": 3,
    "in_vehicle": 4,
    "fall_suspected": 5,
    "abnormal_shock": 5,
}


def normalize_imu_tensor(raw_tensor: List[List[float]]) -> np.ndarray:
    """Normalize 6-axis IMU tensor: accel by 9.80665 m/s^2, gyro by 100.0 dps."""
    arr = np.array(raw_tensor, dtype=np.float32)  # [100, 6]
    if arr.shape != (INPUT_LENGTH, INPUT_CHANNELS):
        raise ValueError(f"Invalid tensor shape {arr.shape} (expected ({INPUT_LENGTH}, {INPUT_CHANNELS}))")
    # Normalize acceleration to ~1g scale and gyro to ~100dps scale
    norm_factors = np.array([9.80665, 9.80665, 9.80665, 100.0, 100.0, 100.0], dtype=np.float32)
    return arr / norm_factors


def load_dataset_from_jsonl(
    jsonl_path: Path,
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """Load windows.jsonl and extract normalized tensors and class targets."""
    tensors: List[np.ndarray] = []
    targets: List[int] = []
    metadata: List[Dict[str, Any]] = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            raw_tensor = record.get("raw_tensor")
            pseudo_label = record.get("pseudo_label", {})
            class_name = pseudo_label.get("class_name")

            if raw_tensor and class_name in LABEL_MAP:
                norm_tensor = normalize_imu_tensor(raw_tensor)
                target_idx = LABEL_MAP[class_name]
                tensors.append(norm_tensor)
                targets.append(target_idx)
                metadata.append(record)

    if not tensors:
        raise ValueError(f"No valid labeled windows found in {jsonl_path}")

    X = np.stack(tensors, axis=0)  # [N, 100, 6]
    y = np.array(targets, dtype=np.int64)  # [N]
    return X, y, metadata


def generate_synthetic_dataset(
    samples_per_class: int = 20, seed: int = 42
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate synthetic IMU tensors for dry-run training and testing."""
    rng = np.random.default_rng(seed)
    tensors: List[np.ndarray] = []
    targets: List[int] = []

    for class_idx in range(NUM_CLASSES):
        for _ in range(samples_per_class):
            t = np.linspace(0, 5.0, INPUT_LENGTH, dtype=np.float32)
            tensor = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)

            if class_idx == 0:  # stationary (quiet gravity on z-axis)
                tensor[:, 2] = 9.81 + rng.normal(0, 0.02, INPUT_LENGTH)
                tensor[:, :2] = rng.normal(0, 0.02, (INPUT_LENGTH, 2))
                tensor[:, 3:] = rng.normal(0, 0.1, (INPUT_LENGTH, 3))
            elif class_idx == 1:  # walking (1.6 Hz gait, vertical & forward oscillations, pitch gyro)
                freq = 1.6
                tensor[:, 2] = 9.81 + 3.0 * np.sin(2 * np.pi * freq * t) + rng.normal(0, 0.2, INPUT_LENGTH)
                tensor[:, 0] = 1.5 * np.cos(2 * np.pi * freq * t) + rng.normal(0, 0.1, INPUT_LENGTH)
                tensor[:, 4] = 40.0 * np.sin(2 * np.pi * freq * t) + rng.normal(0, 2.0, INPUT_LENGTH)
            elif class_idx == 2:  # running (3.0 Hz, high amplitude acceleration and gyro)
                freq = 3.0
                tensor[:, 2] = 9.81 + 8.5 * np.sin(2 * np.pi * freq * t) + rng.normal(0, 0.5, INPUT_LENGTH)
                tensor[:, 0] = 4.0 * np.cos(2 * np.pi * freq * t) + rng.normal(0, 0.3, INPUT_LENGTH)
                tensor[:, 4] = 90.0 * np.sin(2 * np.pi * freq * t) + rng.normal(0, 5.0, INPUT_LENGTH)
            elif class_idx == 3:  # cycling (inclined posture, road vibration 8 Hz, steering perturbations)
                freq = 8.0
                tensor[:, 2] = 8.5 + 1.8 * np.sin(2 * np.pi * freq * t) + rng.normal(0, 0.4, INPUT_LENGTH)
                tensor[:, 0] = 4.5 + rng.normal(0, 0.3, INPUT_LENGTH)
                tensor[:, 3:] = rng.normal(0, 15.0, (INPUT_LENGTH, 3))
            elif class_idx == 4:  # in_vehicle (centrifugal turning on ay, braking/acceleration on ax, yaw turns)
                turn_freq = 0.4
                brake_freq = 0.3
                tensor[:, 2] = 9.81 + rng.normal(0, 0.15, INPUT_LENGTH)
                tensor[:, 1] = 1.8 * np.sin(2 * np.pi * turn_freq * t) + rng.normal(0, 0.1, INPUT_LENGTH)
                tensor[:, 0] = 1.2 * np.cos(2 * np.pi * brake_freq * t) + rng.normal(0, 0.1, INPUT_LENGTH)
                tensor[:, 5] = 12.0 * np.sin(2 * np.pi * turn_freq * t) + rng.normal(0, 0.5, INPUT_LENGTH)
            elif class_idx == 5:  # fall_suspected (free fall -> impact deceleration spike -> tumble -> immobility)
                tensor[:, 2] = 9.81 + rng.normal(0, 0.05, INPUT_LENGTH)
                tensor[20:28, 2] = 1.0  # ~0g free fall (0.4s)
                tensor[28:33, 2] = 35.0  # Deceleration spike >3g (0.25s)
                tensor[28:33, 3:6] = rng.uniform(150.0, 250.0, (5, 3))  # Rotational tumble
                tensor[33:, 2] = 9.81 + rng.normal(0, 0.02, 67)  # Immobility

            norm_tensor = normalize_imu_tensor(tensor.tolist())
            tensors.append(norm_tensor)
            targets.append(class_idx)

    return np.stack(tensors, axis=0), np.array(targets, dtype=np.int64)


def train_tinyml_model(
    model: TinyMLEgoStateModel,
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    epochs: int = 50,
    learning_rate: float = 0.015,
    batch_size: int = 16,
) -> Dict[str, Any]:
    """Train the model dense classification layers using Adam optimization.

    To guarantee high convergence stability without PyTorch, dense classification
    layers (fc1 & fc2) are optimized via the Adam algorithm over extracted GAP
    representations.
    """
    num_samples = X_train.shape[0]
    indices = np.arange(num_samples)
    loss_history: List[float] = []

    # One-hot encode targets
    y_one_hot = np.zeros((num_samples, NUM_CLASSES), dtype=np.float32)
    y_one_hot[np.arange(num_samples), y_train] = 1.0

    # Extract feature representations from Conv1D + GAP layers
    gap_features: List[np.ndarray] = []
    for i in range(num_samples):
        x_single = np.expand_dims(X_train[i], axis=0)
        # Pad and conv1
        x_pad = np.pad(x_single, ((0, 0), (2, 2), (0, 0)), mode="constant")
        conv1_w = model.weights["conv1_w"]
        conv1_b = model.weights["conv1_b"]
        out1 = np.zeros((1, 50, 16), dtype=np.float32)
        for step in range(50):
            window = x_pad[:, step * 2 : step * 2 + 5, :]
            out1[:, step, :] = np.tensordot(window, conv1_w, axes=([1, 2], [0, 1])) + conv1_b
        out1 = relu(out1)

        # DW2 + PW2
        out1_pad = np.pad(out1, ((0, 0), (1, 1), (0, 0)), mode="constant")
        dw2_out = np.zeros((1, 25, 16), dtype=np.float32)
        for step in range(25):
            w_slice = out1_pad[:, step * 2 : step * 2 + 3, :]
            dw2_out[:, step, :] = np.sum(w_slice * model.weights["dw2_w"], axis=1) + model.weights["dw2_b"]
        out2 = relu(np.matmul(relu(dw2_out), model.weights["pw2_w"]) + model.weights["pw2_b"])

        # DW3 + PW3
        out2_pad = np.pad(out2, ((0, 0), (1, 1), (0, 0)), mode="constant")
        dw3_out = np.zeros((1, 13, 32), dtype=np.float32)
        for step in range(13):
            w_slice = out2_pad[:, step * 2 : step * 2 + 3, :]
            dw3_out[:, step, :] = np.sum(w_slice * model.weights["dw3_w"], axis=1) + model.weights["dw3_b"]
        out3 = relu(np.matmul(relu(dw3_out), model.weights["pw3_w"]) + model.weights["pw3_b"])

        gap = np.mean(out3, axis=1)  # [1, 64]
        gap_features.append(gap[0])

    H_gap = np.stack(gap_features, axis=0)  # [N, 64]

    # Model dense weights
    W1 = model.weights["fc1_w"].copy()
    b1 = model.weights["fc1_b"].copy()
    W2 = model.weights["fc2_w"].copy()
    b2 = model.weights["fc2_b"].copy()

    # Adam moments
    mW1, vW1 = np.zeros_like(W1), np.zeros_like(W1)
    mb1, vb1 = np.zeros_like(b1), np.zeros_like(b1)
    mW2, vW2 = np.zeros_like(W2), np.zeros_like(W2)
    mb2, vb2 = np.zeros_like(b2), np.zeros_like(b2)

    beta1 = 0.9
    beta2 = 0.999
    eps = 1e-8
    step_count = 0

    rng = np.random.default_rng(42)

    for epoch in range(epochs):
        rng.shuffle(indices)
        epoch_loss = 0.0
        num_batches = int(math.ceil(num_samples / float(batch_size)))

        for b in range(num_batches):
            b_idx = indices[b * batch_size : (b + 1) * batch_size]
            X_b = H_gap[b_idx]        # [B, 64]
            y_b = y_one_hot[b_idx]    # [B, 6]
            B = X_b.shape[0]
            step_count += 1

            # Forward
            z1 = np.matmul(X_b, W1) + b1  # [B, 32]
            a1 = relu(z1)                 # [B, 32]
            logits = np.matmul(a1, W2) + b2  # [B, 6]
            probs = softmax(logits)          # [B, 6]

            # Cross-Entropy Loss
            loss = -np.mean(np.sum(y_b * np.log(np.clip(probs, 1e-12, 1.0)), axis=1))
            epoch_loss += loss * B

            # Backward gradients
            dlogits = (probs - y_b) / B      # [B, 6]
            dW2 = np.matmul(a1.T, dlogits)   # [32, 6]
            db2 = np.sum(dlogits, axis=0)    # [6]

            da1 = np.matmul(dlogits, W2.T)   # [B, 32]
            dz1 = da1 * (z1 > 0).astype(np.float32)  # ReLU derivative
            dW1 = np.matmul(X_b.T, dz1)      # [64, 32]
            db1 = np.sum(dz1, axis=0)        # [32]

            # Adam updates
            for param, grad, m_arr, v_arr in [
                (W2, dW2, mW2, vW2),
                (b2, db2, mb2, vb2),
                (W1, dW1, mW1, vW1),
                (b1, db1, mb1, vb1),
            ]:
                m_arr[:] = beta1 * m_arr + (1.0 - beta1) * grad
                v_arr[:] = beta2 * v_arr + (1.0 - beta2) * (grad ** 2)
                m_hat = m_arr / (1.0 - beta1 ** step_count)
                v_hat = v_arr / (1.0 - beta2 ** step_count)
                param -= learning_rate * m_hat / (np.sqrt(v_hat) + eps)

        mean_loss = epoch_loss / num_samples
        loss_history.append(float(mean_loss))

    model.weights["fc1_w"] = W1.astype(np.float32)
    model.weights["fc1_b"] = b1.astype(np.float32)
    model.weights["fc2_w"] = W2.astype(np.float32)
    model.weights["fc2_b"] = b2.astype(np.float32)

    return {
        "final_loss": round(loss_history[-1], 4),
        "loss_history": [round(l, 4) for l in loss_history],
        "epochs": epochs,
    }


def evaluate_model(
    model: TinyMLEgoStateModel, X: np.ndarray, y: np.ndarray
) -> Dict[str, Any]:
    """Compute overall accuracy, confusion matrix, precision, recall, and F1."""
    num_samples = X.shape[0]
    confusion_matrix = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int32)
    entropies: List[float] = []

    for i in range(num_samples):
        pred = model.predict(X[i])
        pred_idx = pred["class_index"]
        true_idx = y[i]
        confusion_matrix[true_idx, pred_idx] += 1
        entropies.append(pred["entropy"])

    correct = int(np.trace(confusion_matrix))
    accuracy = float(correct / num_samples) if num_samples > 0 else 0.0

    class_metrics: Dict[str, Dict[str, float]] = {}
    for c_idx, c_name in enumerate(CLASS_NAMES):
        tp = float(confusion_matrix[c_idx, c_idx])
        fp = float(np.sum(confusion_matrix[:, c_idx]) - tp)
        fn = float(np.sum(confusion_matrix[c_idx, :]) - tp)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        class_metrics[c_name] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "support": int(np.sum(confusion_matrix[c_idx, :])),
        }

    return {
        "num_samples": num_samples,
        "accuracy": round(accuracy, 4),
        "mean_entropy": round(float(np.mean(entropies)), 4) if entropies else 0.0,
        "confusion_matrix": confusion_matrix.tolist(),
        "class_metrics": class_metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate TinyML edge model")
    parser.add_argument("--dataset-jsonl", type=Path, help="Path to harvested windows.jsonl")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/models/tinyml_v1"), help="Output directory")
    parser.add_argument("--epochs", type=int, default=20, help="Training epochs")
    parser.add_argument("--lr", type=float, default=0.03, help="Learning rate")
    parser.add_argument("--dry-run", action="store_true", help="Use synthetic dataset if no file specified")

    args = parser.parse_args()

    if args.dataset_jsonl and args.dataset_jsonl.is_file():
        print(f"Loading harvested dataset from {args.dataset_jsonl}...")
        X, y, _ = load_dataset_from_jsonl(args.dataset_jsonl)
    elif args.dry_run or not args.dataset_jsonl:
        print("Generating synthetic 6-class dataset for training and verification...")
        X, y = generate_synthetic_dataset(samples_per_class=30, seed=42)
    else:
        print(f"Error: Dataset file not found: {args.dataset_jsonl}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {X.shape[0]} samples with shape {X.shape[1:]}.")

    # Split 80/20 train/test
    rng = np.random.default_rng(42)
    perm = rng.permutation(X.shape[0])
    split_idx = int(0.8 * X.shape[0])
    train_idx, test_idx = perm[:split_idx], perm[split_idx:]

    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]

    model = TinyMLEgoStateModel(seed=42)
    print("Pre-training evaluation:")
    pre_eval = evaluate_model(model, X_test, y_test)
    print(f"  Initial Accuracy: {pre_eval['accuracy'] * 100:.2f}%")

    print(f"Training TinyML model for {args.epochs} epochs (LR={args.lr})...")
    train_result = train_tinyml_model(model, X_train, y_train, epochs=args.epochs, learning_rate=args.lr)
    print(f"  Final Loss: {train_result['final_loss']}")

    print("Post-training evaluation on test set:")
    eval_metrics = evaluate_model(model, X_test, y_test)
    print(f"  Test Accuracy: {eval_metrics['accuracy'] * 100:.2f}%")
    print(f"  Mean Entropy: {eval_metrics['mean_entropy']}")
    print(f"  Class Metrics: {json.dumps(eval_metrics['class_metrics'], indent=2)}")

    footprint = model.get_parameter_count()
    print(f"Model Memory Footprint: {footprint['int8_footprint_kb']} KB INT8 ({footprint['total_parameters']} params)")
    print(f"Fits in SRAM (<30KB): {footprint['fits_in_sram_under_30kb']}")

    # Export artifacts
    args.output_dir.mkdir(parents=True, exist_ok=True)
    c_header_path = args.output_dir / "tinyml_ego_state_weights.h"
    model.export_c_header(c_header_path)
    print(f"Exported C-header to: {c_header_path}")

    report = {
        "training": train_result,
        "evaluation": eval_metrics,
        "footprint": footprint,
    }
    report_path = args.output_dir / "model_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved evaluation report to: {report_path}")


if __name__ == "__main__":
    main()
