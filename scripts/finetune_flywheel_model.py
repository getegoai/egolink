"""Continuous Learning Flywheel Retraining & Model Packaging Pipeline (AI-040).

This module closes the autonomous data flywheel loop:
1. Ingests mined Ambiguity Gold Samples from Phase 3 (`mined_gold_samples.jsonl`).
2. Blends gold samples with historical anchor windows to prevent catastrophic forgetting.
3. Fine-tunes the 1D-CNN edge model using Adam with regularization.
4. Executes the mandatory Safety Regression Gate (zero tolerance for fall/SOS misses).
5. Packages candidate weights into a cryptographically verified binary OTA image
   (`EGO_WGT1` format with SHA-256 checksum) and updated C header.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
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
    calculate_entropy,
)
from pc_simulator.safety_kernel_arbitrator import SafetyKernelArbitrator
from scripts.train_edge_tinyml_model import (
    LABEL_MAP,
    normalize_imu_tensor,
    generate_synthetic_dataset,
    train_tinyml_model,
    evaluate_model,
)

BINARY_MAGIC = b"EGO_WGT1"  # 8 bytes magic header


class SafetyRegressionError(Exception):
    """Raised when a candidate model fails the Safety Regression Gate."""
    pass


def load_gold_samples(gold_jsonl_path: Path) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """Load and parse mined gold samples into normalized tensors and target classes."""
    tensors: List[np.ndarray] = []
    targets: List[int] = []
    metadata: List[Dict[str, Any]] = []

    with open(gold_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            raw_tensor = rec.get("raw_tensor")
            arbitrated_state = rec.get("arbitrated_state")
            tinyml_state = rec.get("tinyml_state")
            conflict_desc = rec.get("conflict_description", "")

            # If it was a treadmill conflict (e.g. running IMU with 0 m/s GNSS),
            # the true biomechanical mobility target is running
            target_name = arbitrated_state
            if "predicts 'running'" in conflict_desc:
                target_name = "running"
            elif "predicts 'walking'" in conflict_desc:
                target_name = "walking"

            if raw_tensor and target_name in LABEL_MAP:
                norm_tensor = normalize_imu_tensor(raw_tensor)
                target_idx = LABEL_MAP[target_name]
                tensors.append(norm_tensor)
                targets.append(target_idx)
                metadata.append(rec)

    if not tensors:
        raise ValueError(f"No valid gold samples found in {gold_jsonl_path}")

    X = np.stack(tensors, axis=0)
    y = np.array(targets, dtype=np.int64)
    return X, y, metadata


def blend_with_anchor_replay_buffer(
    X_gold: np.ndarray,
    y_gold: np.ndarray,
    *,
    anchors_per_class: int = 15,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Blend newly mined gold samples with anchor baseline dataset to prevent forgetting."""
    X_anchor, y_anchor = generate_synthetic_dataset(samples_per_class=anchors_per_class, seed=seed)
    X_blended = np.concatenate([X_gold, X_anchor], axis=0)
    y_blended = np.concatenate([y_gold, y_anchor], axis=0)

    # Shuffle combined dataset
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(y_blended))
    return X_blended[perm], y_blended[perm]


def build_golden_safety_benchmark(seed: int = 100) -> List[Dict[str, Any]]:
    """Generate unambiguous golden safety test vectors (falls and severe impacts)."""
    rng = np.random.default_rng(seed)
    vectors: List[Dict[str, Any]] = []

    # 10 Fall Scenarios: Free-fall -> massive impact (> 30 m/s^2) -> complete immobility
    for i in range(10):
        t = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        t[:, 2] = 9.81 + rng.normal(0, 0.05, INPUT_LENGTH)
        # 0g freefall
        t[18:25, 2] = 0.5 + rng.normal(0, 0.1, 7)
        # Impact deceleration spike
        t[25:30, 2] = rng.uniform(32.0, 48.0, 5)
        t[25:30, 3:6] = rng.uniform(150.0, 300.0, (5, 3))
        # Post-impact quiet
        t[30:, 2] = 9.81 + rng.normal(0, 0.02, 70)
        vectors.append({
            "vector_id": f"golden-fall-{i:02d}",
            "raw_tensor": t.tolist(),
            "context": {"gnss_speed_mps": 0.0, "is_charging": False},
            "expected_safety_category": "fall_suspected",
        })

    # 5 Abnormal Mechanical Shocks (> 30 m/s^2 without post-fall immobility)
    for i in range(5):
        t = np.zeros((INPUT_LENGTH, INPUT_CHANNELS), dtype=np.float32)
        t[:, 2] = 9.81 + rng.normal(0, 0.2, INPUT_LENGTH)
        t[40:44, 2] = rng.uniform(30.0, 45.0, 4)
        vectors.append({
            "vector_id": f"golden-shock-{i:02d}",
            "raw_tensor": t.tolist(),
            "context": {"gnss_speed_mps": 1.5},
            "expected_safety_category": "abnormal_shock",
        })

    return vectors


def run_safety_regression_gate(
    model: TinyMLEgoStateModel,
    arbitrator: Optional[SafetyKernelArbitrator] = None,
) -> Dict[str, Any]:
    """Verify that candidate model and arbitrator maintain 100% recall on golden safety vectors.

    Raises:
        SafetyRegressionError: If any golden safety vector is missed or downgraded.
    """
    if arbitrator is None:
        arbitrator = SafetyKernelArbitrator(model)

    golden_vectors = build_golden_safety_benchmark()
    total_vectors = len(golden_vectors)
    passed_count = 0
    failures: List[Dict[str, Any]] = []

    for vec in golden_vectors:
        res = arbitrator.arbitrate_window(
            vec["raw_tensor"],
            vec["context"],
            window_id=vec["vector_id"],
        )
        expected = vec["expected_safety_category"]
        actual = res["arbitrated_state"]

        # Check safety outcome: must match expected safety event and trigger safety priority
        is_safe = (
            (expected == "fall_suspected" and actual == "fall_suspected" and res["is_safety_override"])
            or (expected == "abnormal_shock" and actual in ("abnormal_shock", "fall_suspected"))
        )

        if is_safe:
            passed_count += 1
        else:
            failures.append({
                "vector_id": vec["vector_id"],
                "expected": expected,
                "actual": actual,
                "arbitration_reason": res["arbitration_reason"],
            })

    if failures:
        msg = f"Safety Regression Gate FAILED: {len(failures)}/{total_vectors} vectors failed!\n{json.dumps(failures, indent=2)}"
        raise SafetyRegressionError(msg)

    return {
        "gate_status": "PASSED",
        "total_safety_vectors_tested": total_vectors,
        "passed_vectors": passed_count,
        "recall": 1.0,
    }


def package_model_binary(
    model: TinyMLEgoStateModel,
    output_bin_path: Path,
    *,
    model_version: int = 2,
) -> Dict[str, Any]:
    """Serialize model weights into an INT8 binary OTA image with SHA-256 checksum.

    Binary Layout:
    - 8 bytes: Magic b"EGO_WGT1"
    - 2 bytes: Format version (uint16 = 1)
    - 2 bytes: Model version (uint16)
    - 8 bytes: Unix timestamp (uint64)
    - 2 bytes: Num classes (uint16 = 6)
    - 4 bytes: Total parameters (uint32)
    - 2 bytes: Number of layer blocks (uint16)
    - For each layer:
        - 2 bytes: Name length (uint16)
        - N bytes: Layer name (ASCII)
        - 4 bytes: Scale (float32)
        - 2 bytes: Dims count (uint16)
        - D*2 bytes: Dimension values (uint16 each)
        - 4 bytes: Payload byte length (uint32)
        - P bytes: Raw INT8 weights
    - 32 bytes: Cryptographic SHA-256 digest of entire preceding payload
    """
    quantized = model.quantize_int8()
    meta = model.get_parameter_count()

    header_buf = bytearray()
    # Magic + format_ver (1) + model_ver + timestamp + num_classes (6) + total_params + num_layers
    header_buf.extend(BINARY_MAGIC)
    now_ts = int(time.time())
    header_buf.extend(struct.pack("<HHQHIH", 1, model_version, now_ts, NUM_CLASSES, meta["total_parameters"], len(quantized)))

    body_buf = bytearray()
    for name, data in quantized.items():
        name_bytes = name.encode("ascii")
        body_buf.extend(struct.pack("<H", len(name_bytes)))
        body_buf.extend(name_bytes)
        body_buf.extend(struct.pack("<f", float(data["scale"])))

        shape = data["shape"]
        body_buf.extend(struct.pack("<H", len(shape)))
        for dim in shape:
            body_buf.extend(struct.pack("<H", int(dim)))

        int8_vals = bytes(np.array(data["int8_values"], dtype=np.int8).tobytes())
        body_buf.extend(struct.pack("<I", len(int8_vals)))
        body_buf.extend(int8_vals)

    payload_before_checksum = header_buf + body_buf
    sha256_digest = hashlib.sha256(payload_before_checksum).digest()  # 32 bytes
    full_binary = payload_before_checksum + sha256_digest

    output_bin_path.parent.mkdir(parents=True, exist_ok=True)
    output_bin_path.write_bytes(full_binary)

    return {
        "binary_path": str(output_bin_path),
        "binary_size_bytes": len(full_binary),
        "binary_size_kb": round(len(full_binary) / 1024.0, 2),
        "model_version": model_version,
        "total_parameters": meta["total_parameters"],
        "sha256_hex": sha256_digest.hex(),
    }


def verify_model_binary(bin_path: Path) -> Dict[str, Any]:
    """Verify integrity and parse metadata from a packaged model binary."""
    raw = bin_path.read_bytes()
    if len(raw) < 56:
        raise ValueError("Binary size too small for header and checksum")

    content, expected_checksum = raw[:-32], raw[-32:]
    actual_checksum = hashlib.sha256(content).digest()

    if actual_checksum != expected_checksum:
        raise ValueError(f"Checksum mismatch! Expected {expected_checksum.hex()}, got {actual_checksum.hex()}")

    magic = content[:8]
    if magic != BINARY_MAGIC:
        raise ValueError(f"Invalid magic header: {magic}")

    fmt_ver, model_ver, timestamp, num_classes, total_params, num_layers = struct.unpack("<HHQHIH", content[8:28])

    return {
        "is_valid": True,
        "format_version": fmt_ver,
        "model_version": model_ver,
        "timestamp": timestamp,
        "num_classes": num_classes,
        "total_parameters": total_params,
        "num_layers": num_layers,
        "sha256_hex": actual_checksum.hex(),
        "binary_bytes": len(raw),
    }


def finetune_flywheel_model(
    base_model: TinyMLEgoStateModel,
    gold_samples_path: Path,
    output_dir: Path,
    *,
    model_version: int = 2,
    epochs: int = 40,
    learning_rate: float = 0.008,
) -> Dict[str, Any]:
    """Execute complete flywheel fine-tuning, safety gating, and packaging pipeline."""
    # 1. Load Gold Samples and blend with replay buffer
    X_gold, y_gold, gold_meta = load_gold_samples(gold_samples_path)
    X_train, y_train = blend_with_anchor_replay_buffer(X_gold, y_gold, anchors_per_class=15, seed=42)

    # 2. Pre-tuning evaluation on gold samples
    pre_eval = evaluate_model(base_model, X_gold, y_gold)

    # 3. Fine-tune model
    train_res = train_tinyml_model(
        base_model,
        X_train,
        y_train,
        epochs=epochs,
        learning_rate=learning_rate,
        batch_size=16,
    )

    # 4. Post-tuning evaluation on gold samples
    post_eval = evaluate_model(base_model, X_gold, y_gold)

    # 5. Safety Regression Gate Verification
    safety_gate_res = run_safety_regression_gate(base_model)

    # 6. Cryptographic Packaging & C-Header Export
    output_dir.mkdir(parents=True, exist_ok=True)
    bin_path = output_dir / f"ego_model_v{model_version}.bin"
    pkg_info = package_model_binary(base_model, bin_path, model_version=model_version)

    c_header_path = output_dir / f"tinyml_ego_state_weights_v{model_version}.h"
    base_model.export_c_header(c_header_path)

    # Verification readback
    verify_info = verify_model_binary(bin_path)

    report = {
        "pipeline": "AI-040 Continuous Fine-Tuning & Model Packaging",
        "timestamp": int(time.time()),
        "model_version": model_version,
        "gold_samples_count": len(gold_meta),
        "total_training_samples": len(y_train),
        "pre_eval_accuracy": pre_eval["accuracy"],
        "post_eval_accuracy": post_eval["accuracy"],
        "training_history": train_res,
        "safety_regression_gate": safety_gate_res,
        "packaging": pkg_info,
        "verification": verify_info,
    }

    # Save JSON and Markdown report
    report_path = output_dir / "retraining_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# Flywheel Continuous Retraining & Packaging Report (v{model_version})",
        "",
        f"**Date**: 2026-09-23  ",
        f"**Model Version**: v{model_version}  ",
        f"**Safety Gate**: {safety_gate_res['gate_status']} (100% recall on golden safety test vectors)  ",
        "",
        "## Performance Progression",
        "",
        f"- **Gold Samples Trained**: {len(gold_meta)}",
        f"- **Total Blended Dataset**: {len(y_train)} (Gold Samples + Anchor Replay Buffer)",
        f"- **Pre-Tuning Accuracy on Gold Samples**: {pre_eval['accuracy'] * 100:.2f}%",
        f"- **Post-Tuning Accuracy on Gold Samples**: {post_eval['accuracy'] * 100:.2f}%",
        f"- **Final Training Loss**: {train_res['final_loss']}",
        "",
        "## Packaging and Integrity",
        "",
        f"- **Binary OTA Image**: `{bin_path.name}` ({pkg_info['binary_size_kb']} KB)",
        f"- **C Header Export**: `{c_header_path.name}`",
        f"- **SHA-256 Checksum**: `{pkg_info['sha256_hex']}`",
        f"- **Binary Integrity Verified**: `{verify_info['is_valid']}`",
        "",
    ]
    (output_dir / "retraining_report.md").write_text("\n".join(md_lines), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Flywheel Continuous Retraining Pipeline")
    parser.add_argument(
        "--gold-samples",
        type=Path,
        default=Path("reports/models/shadow_v1/mined_gold_samples.jsonl"),
        help="Path to mined gold samples JSONL",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/models/flywheel_v2"),
        help="Output directory for new model package",
    )
    parser.add_argument("--model-version", type=int, default=2, help="Model version integer")
    parser.add_argument("--epochs", type=int, default=40, help="Training epochs")
    parser.add_argument("--lr", type=float, default=0.008, help="Fine-tuning learning rate")

    args = parser.parse_args()

    if not args.gold_samples.is_file():
        print(f"Error: Gold samples file not found: {args.gold_samples}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading initial model and gold samples from {args.gold_samples}...")
    base_model = TinyMLEgoStateModel(seed=42)

    report = finetune_flywheel_model(
        base_model,
        args.gold_samples,
        args.output_dir,
        model_version=args.model_version,
        epochs=args.epochs,
        learning_rate=args.lr,
    )

    print("\nFlywheel Continuous Retraining Completed Successfully!")
    print(f"  Model Version: v{report['model_version']}")
    print(f"  Pre-tuning Accuracy: {report['pre_eval_accuracy'] * 100:.2f}%")
    print(f"  Post-tuning Accuracy: {report['post_eval_accuracy'] * 100:.2f}%")
    print(f"  Safety Gate: {report['safety_regression_gate']['gate_status']}")
    print(f"  Binary OTA Package: {report['packaging']['binary_path']} ({report['packaging']['binary_size_kb']} KB)")
    print(f"  SHA-256: {report['packaging']['sha256_hex']}")


if __name__ == "__main__":
    main()
