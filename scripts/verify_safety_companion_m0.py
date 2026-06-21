"""Verify the Safety Companion M0 overlay without external dependencies."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "MODEL_PACKAGE_README.md",
    "docs/modeling/SAFETY_COMPANION_ARCHITECTURE.md",
    "docs/modeling/DATA_COLLECTION_SPEC.md",
    "docs/modeling/MODEL_HANDOFF.md",
    "docs/modeling/INTEGRATION_TASKS.md",
    "shared/contracts/sensor_frame.schema.json",
    "shared/contracts/model_input.schema.json",
    "shared/contracts/model_output.schema.json",
    "shared/contracts/safety_event.schema.json",
    "shared/contracts/base_command.schema.json",
    "shared/contracts/safety_annotation.schema.json",
    "shared/embedded/safety_model_contract.h",
    "model_lab/safety_companion/src/baseline_router.py",
    "model_lab/safety_companion/datasets/samples/scenario_suite.json",
    "model_artifacts/safety_companion/rule_router/0.1.0/model_config.json",
]


def run(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    print("$", " ".join(command))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def check_required() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit("Missing required files:\n" + "\n".join(f"- {item}" for item in missing))
    print(f"Required files: {len(REQUIRED)} present")


def check_generated_header() -> None:
    config = ROOT / "model_lab/safety_companion/configs/router_v0.1.0.json"
    committed = ROOT / "model_artifacts/safety_companion/rule_router/0.1.0/include/safety_router_thresholds.h"
    generator = ROOT / "model_lab/safety_companion/export/generate_c_header.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        generated = Path(temp_dir) / "safety_router_thresholds.h"
        run("Generate C thresholds", [sys.executable, str(generator), str(config), str(generated)])
        expected = committed.read_bytes()
        actual = generated.read_bytes()
        if expected != actual:
            raise SystemExit("Generated threshold header does not match committed artifact")
        digest = hashlib.sha256(actual).hexdigest()
        print(f"Generated header matches artifact: sha256={digest}")


def main() -> int:
    print(f"Safety Companion M0 root: {ROOT}")
    check_required()
    run(
        "Contract quality tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "quality_tests/model_contract", "-p", "test_*.py", "-v"],
    )
    run(
        "Package unit tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "model_lab/safety_companion/tests", "-p", "test_*.py", "-v"],
    )
    run("Scenario demo", [sys.executable, "-m", "model_lab.safety_companion.src.cli", "demo"])
    run("Baseline evaluation", [sys.executable, "model_lab/safety_companion/evaluation/evaluate_baseline.py"])
    check_generated_header()
    print("\nSafety Companion M0 verification PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
