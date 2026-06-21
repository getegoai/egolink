"""Convert recorded sensor-frame JSONL into normalized model-input JSONL.

M0 does not train a neural network yet. This tool creates the versioned feature
records that later MotionNet/AudioGate/ContextRouter experiments will consume.
"""

from __future__ import annotations

import argparse

from model_lab.safety_companion.src.feature_extractor import build_model_input
from model_lab.safety_companion.src.replay import iter_jsonl, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="sensor-frame JSONL")
    parser.add_argument("output", help="model-input JSONL")
    args = parser.parse_args()
    values = [build_model_input(frame) for frame in iter_jsonl(args.input)]
    write_jsonl(args.output, values)
    print(f"Converted {len(values)} sensor frames into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
