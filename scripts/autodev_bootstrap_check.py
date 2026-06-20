#!/usr/bin/env python3
"""Deterministic external checks for the initial AutoDev smoke tasks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def check_auto_001() -> list[str]:
    path = REPO_ROOT / "docs" / "repository_baseline.md"
    errors: list[str] = []
    if not path.is_file():
        return [f"missing file: {path}"]

    text = path.read_text(encoding="utf-8", errors="replace")
    required = (
        "# Ego Link Repository Baseline",
        "## Current Structure",
        "## Verified Commands",
        "## P0 Boundary",
        "## Risks and Gaps",
    )
    for marker in required:
        if marker not in text:
            errors.append(f"missing required heading: {marker}")
    if len(text.strip()) < 500:
        errors.append("baseline document is too short to be useful (minimum 500 characters)")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id", choices=("AUTO-001",))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.task_id == "AUTO-001":
        errors = check_auto_001()
    else:  # pragma: no cover - guarded by argparse choices
        errors = [f"unsupported task: {args.task_id}"]

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: {args.task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
