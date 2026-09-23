"""TinyML 1D-CNN Ego-State estimation edge model for ESP32-S3 (AI-020).

This module implements the edge neural network architecture defined in ADR-0017
and AI_NATIVE_EGO_STATE_FLYWHEEL.md:
- Input: [100, 6] (100 timesteps @ 20Hz, 6 IMU axes: ax, ay, az, gx, gy, gz)
- Topology:
    Layer 1: Conv1D(16, k=5, s=2) + ReLU
    Layer 2: DepthwiseConv1D(k=3, s=2) + PointwiseConv1D(32) + ReLU
    Layer 3: DepthwiseConv1D(k=3, s=2) + PointwiseConv1D(64) + ReLU
    Layer 4: GlobalAveragePooling1D -> [64]
    Layer 5: Dense(32) + ReLU
    Layer 6: Dense(6) + Softmax
- Footprint: ~5.6 KB in INT8 (under the 30 KB budget for ESP32-S3 internal SRAM).
- Target Primitives (6 classes):
    0: stationary
    1: walking
    2: running
    3: cycling
    4: in_vehicle
    5: fall_suspected
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


CLASS_NAMES: List[str] = [
    "stationary",       # 0
    "walking",          # 1
    "running",          # 2
    "cycling",          # 3
    "in_vehicle",       # 4
    "fall_suspected",   # 5
]
NUM_CLASSES = len(CLASS_NAMES)
INPUT_LENGTH = 100
INPUT_CHANNELS = 6


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


def softmax(x: np.ndarray) -> np.ndarray:
    """Stable softmax along the last axis."""
    e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e_x / np.sum(e_x, axis=-1, keepdims=True)


def calculate_entropy(probs: np.ndarray) -> float:
    """Calculate Shannon entropy H(p) = -sum(p * log2(p))."""
    eps = 1e-12
    p = np.clip(probs, eps, 1.0)
    return float(-np.sum(p * np.log2(p)))


class TinyMLEgoStateModel:
    """1D-CNN edge inference model for micro-motion classification."""

    def __init__(self, weights: Optional[Dict[str, np.ndarray]] = None, seed: int = 42):
        self.weights: Dict[str, np.ndarray] = {}
        if weights is not None:
            self.weights = weights
        else:
            self._init_weights(seed)

    def _init_weights(self, seed: int) -> None:
        rng = np.random.default_rng(seed)

        def he_normal(fan_in: int, shape: Tuple[int, ...]) -> np.ndarray:
            std = math.sqrt(2.0 / fan_in)
            return rng.normal(0.0, std, size=shape).astype(np.float32)

        # Layer 1: Conv1D (k=5, in=6, out=16, stride=2)
        self.weights["conv1_w"] = he_normal(5 * 6, (5, 6, 16))
        self.weights["conv1_b"] = np.zeros(16, dtype=np.float32)

        # Layer 2: Depthwise Separable Conv1D
        # Depthwise (k=3, channels=16, stride=2)
        self.weights["dw2_w"] = he_normal(3, (3, 16))
        self.weights["dw2_b"] = np.zeros(16, dtype=np.float32)
        # Pointwise (in=16, out=32, stride=1)
        self.weights["pw2_w"] = he_normal(16, (16, 32))
        self.weights["pw2_b"] = np.zeros(32, dtype=np.float32)

        # Layer 3: Depthwise Separable Conv1D
        # Depthwise (k=3, channels=32, stride=2)
        self.weights["dw3_w"] = he_normal(3, (3, 32))
        self.weights["dw3_b"] = np.zeros(32, dtype=np.float32)
        # Pointwise (in=32, out=64, stride=1)
        self.weights["pw3_w"] = he_normal(32, (32, 64))
        self.weights["pw3_b"] = np.zeros(64, dtype=np.float32)

        # Layer 5: Dense (64 -> 32)
        self.weights["fc1_w"] = he_normal(64, (64, 32))
        self.weights["fc1_b"] = np.zeros(32, dtype=np.float32)

        # Layer 6: Dense (32 -> 6)
        self.weights["fc2_w"] = he_normal(32, (32, NUM_CLASSES))
        self.weights["fc2_b"] = np.zeros(NUM_CLASSES, dtype=np.float32)

    def forward(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Forward pass through the 1D-CNN.

        Input:
            x: shape [100, 6] or [batch, 100, 6]
        Returns:
            probs: softmax class probabilities [6] or [batch, 6]
            logits: pre-softmax activations [6] or [batch, 6]
        """
        is_single = (x.ndim == 2)
        if is_single:
            x = np.expand_dims(x, axis=0)  # [1, 100, 6]

        batch_size = x.shape[0]

        # 1. Conv1D (k=5, in=6, out=16, s=2)
        # Padding 'same' with odd kernel (pad=2 on both sides)
        x_pad = np.pad(x, ((0, 0), (2, 2), (0, 0)), mode="constant")
        conv1_w = self.weights["conv1_w"]  # [5, 6, 16]
        conv1_b = self.weights["conv1_b"]  # [16]
        # Output length: ceil(100 / 2) = 50
        out_len1 = 50
        out1 = np.zeros((batch_size, out_len1, 16), dtype=np.float32)
        for i in range(out_len1):
            window = x_pad[:, i * 2 : i * 2 + 5, :]  # [batch, 5, 6]
            # Tensor contraction over kernel and channels
            out1[:, i, :] = np.tensordot(window, conv1_w, axes=([1, 2], [0, 1])) + conv1_b
        out1 = relu(out1)

        # 2. Depthwise Separable Conv1D (stride=2)
        # Depthwise (k=3, channels=16, s=2)
        out1_pad = np.pad(out1, ((0, 0), (1, 1), (0, 0)), mode="constant")
        dw2_w = self.weights["dw2_w"]  # [3, 16]
        dw2_b = self.weights["dw2_b"]  # [16]
        out_len2 = 25
        dw2_out = np.zeros((batch_size, out_len2, 16), dtype=np.float32)
        for i in range(out_len2):
            w_slice = out1_pad[:, i * 2 : i * 2 + 3, :]  # [batch, 3, 16]
            dw2_out[:, i, :] = np.sum(w_slice * dw2_w, axis=1) + dw2_b
        dw2_out = relu(dw2_out)

        # Pointwise (16 -> 32)
        pw2_w = self.weights["pw2_w"]  # [16, 32]
        pw2_b = self.weights["pw2_b"]  # [32]
        out2 = np.matmul(dw2_out, pw2_w) + pw2_b
        out2 = relu(out2)

        # 3. Depthwise Separable Conv1D (stride=2)
        # Depthwise (k=3, channels=32, s=2)
        out2_pad = np.pad(out2, ((0, 0), (1, 1), (0, 0)), mode="constant")
        dw3_w = self.weights["dw3_w"]  # [3, 32]
        dw3_b = self.weights["dw3_b"]  # [32]
        out_len3 = 13
        dw3_out = np.zeros((batch_size, out_len3, 32), dtype=np.float32)
        for i in range(out_len3):
            w_slice = out2_pad[:, i * 2 : i * 2 + 3, :]  # [batch, 3, 32]
            dw3_out[:, i, :] = np.sum(w_slice * dw3_w, axis=1) + dw3_b
        dw3_out = relu(dw3_out)

        # Pointwise (32 -> 64)
        pw3_w = self.weights["pw3_w"]  # [32, 64]
        pw3_b = self.weights["pw3_b"]  # [64]
        out3 = np.matmul(dw3_out, pw3_w) + pw3_b
        out3 = relu(out3)

        # 4. Global Average Pooling (aggregates out_len3=13 -> [batch, 64])
        gap = np.mean(out3, axis=1)  # [batch, 64]

        # 5. Dense (64 -> 32) + ReLU
        fc1_w = self.weights["fc1_w"]  # [64, 32]
        fc1_b = self.weights["fc1_b"]  # [32]
        dense1 = relu(np.matmul(gap, fc1_w) + fc1_b)

        # 6. Dense (32 -> 6)
        fc2_w = self.weights["fc2_w"]  # [32, 6]
        fc2_b = self.weights["fc2_b"]  # [6]
        logits = np.matmul(dense1, fc2_w) + fc2_b  # [batch, 6]

        probs = softmax(logits)

        if is_single:
            return probs[0], logits[0]
        return probs, logits

    def predict(self, x: np.ndarray) -> Dict[str, Any]:
        """Predict class name, confidence and prediction entropy."""
        probs, logits = self.forward(x)
        class_idx = int(np.argmax(probs))
        confidence = float(probs[class_idx])
        entropy = calculate_entropy(probs)

        return {
            "class_index": class_idx,
            "class_name": CLASS_NAMES[class_idx],
            "confidence": round(confidence, 4),
            "entropy": round(entropy, 4),
            "probabilities": {name: round(float(p), 4) for name, p in zip(CLASS_NAMES, probs)},
        }

    def get_parameter_count(self) -> Dict[str, Any]:
        """Calculate total parameter counts and byte footprints."""
        breakdown: Dict[str, int] = {}
        total_params = 0
        for name, param in self.weights.items():
            count = int(param.size)
            breakdown[name] = count
            total_params += count

        float32_bytes = total_params * 4
        int8_bytes = total_params * 1  # 1 byte per weight

        return {
            "total_parameters": total_params,
            "int8_footprint_bytes": int8_bytes,
            "int8_footprint_kb": round(int8_bytes / 1024.0, 2),
            "float32_footprint_bytes": float32_bytes,
            "float32_footprint_kb": round(float32_bytes / 1024.0, 2),
            "fits_in_sram_under_30kb": int8_bytes < 30 * 1024,
            "layer_breakdown": breakdown,
        }

    def quantize_int8(self) -> Dict[str, Any]:
        """Symmetric INT8 quantization of weights: W_int8 = clip(round(W / scale), -128, 127)."""
        quantized: Dict[str, Any] = {}
        for name, w in self.weights.items():
            max_abs = float(np.max(np.abs(w)))
            scale = max_abs / 127.0 if max_abs > 0 else 1.0
            q_w = np.clip(np.round(w / scale), -128, 127).astype(np.int8)
            quantized[name] = {
                "int8_values": q_w.flatten().tolist(),
                "shape": list(w.shape),
                "scale": float(scale),
            }
        return quantized

    def export_c_header(self, output_path: Path) -> None:
        """Export quantized INT8 model weights as a C header file for ESP32-S3."""
        q = self.quantize_int8()
        meta = self.get_parameter_count()

        lines: List[str] = [
            "/* Generated by EgoLink TinyML Engine (AI-020). DO NOT EDIT MANUALLY. */",
            f"/* Total parameters: {meta['total_parameters']} ({meta['int8_footprint_kb']} KB INT8) */",
            "#pragma once",
            "",
            "#include <stdint.h>",
            "",
            f"#define TINYML_INPUT_LENGTH {INPUT_LENGTH}",
            f"#define TINYML_INPUT_CHANNELS {INPUT_CHANNELS}",
            f"#define TINYML_NUM_CLASSES {NUM_CLASSES}",
            "",
        ]

        for name, data in q.items():
            values = data["int8_values"]
            scale = data["scale"]
            lines.append(f"/* Layer: {name}, Shape: {data['shape']}, Scale: {scale:.8f} */")
            lines.append(f"static const float {name}_scale = {scale:.8f}f;")
            lines.append(f"static const int8_t {name}_weights[{len(values)}] = {{")
            # Format in chunks of 16 numbers per line
            for i in range(0, len(values), 16):
                chunk = values[i : i + 16]
                line_str = "    " + ", ".join(f"{v:4d}" for v in chunk) + ","
                lines.append(line_str)
            lines.append("};")
            lines.append("")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
