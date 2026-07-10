"""Command-line interface for package verification and PC-side integration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .baseline_router import RuleRouter
from .contract_validation import ContractValidationError, load_json, load_schema, validate_instance
from .feature_extractor import build_model_input
from .replay import iter_jsonl, replay_model_inputs, replay_sensor_frames, write_jsonl
from .scenario_generator import build_scenario_suite, sample_sensor_frames


SCHEMA_BY_KIND = {
    "sensor-frame": "sensor_frame.schema.json",
    "model-input": "model_input.schema.json",
    "model-output": "model_output.schema.json",
    "safety-event": "safety_event.schema.json",
    "base-command": "base_command.schema.json",
    "annotation": "safety_annotation.schema.json",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ego Link Safety Companion M0 tools")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run all bundled synthetic scenarios")
    demo.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    validate = sub.add_parser("validate", help="validate a JSON or JSONL file")
    validate.add_argument("kind", choices=sorted(SCHEMA_BY_KIND))
    validate.add_argument("path")
    validate.add_argument("--jsonl", action="store_true")

    replay = sub.add_parser("replay", help="replay JSONL through the rule router")
    replay.add_argument("kind", choices=["sensor-frame", "model-input"])
    replay.add_argument("input")
    replay.add_argument("--output", required=True)

    generate = sub.add_parser("generate-samples", help="write deterministic sample files")
    generate.add_argument("output_dir")

    return parser


def cmd_demo(as_json: bool) -> int:
    router = RuleRouter()
    rows: list[dict[str, Any]] = []
    failures = 0
    for scenario in build_scenario_suite():
        result = router.evaluate(scenario["input"])
        expected = scenario["expected"]
        passed = (
            result["risk_type"] == expected["risk_type"]
            and result["recommended_action"] == expected["recommended_action"]
            and result["priority"] == expected["priority"]
            and not set(expected.get("forbidden_evidence", [])) & set(result["evidence_request"])
        )
        failures += int(not passed)
        rows.append({"id": scenario["id"], "passed": passed, "expected": expected, "result": result})

    if as_json:
        print(json.dumps({"passed": failures == 0, "scenarios": rows}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            marker = "PASS" if row["passed"] else "FAIL"
            result = row["result"]
            print(f"[{marker}] {row['id']}: {result['risk_type']} -> {result['recommended_action']} ({result['priority']})")
        print(f"Summary: {len(rows) - failures}/{len(rows)} passed")
    return 0 if failures == 0 else 1


def cmd_validate(kind: str, path: str, jsonl: bool) -> int:
    schema = load_schema(SCHEMA_BY_KIND[kind])
    try:
        if jsonl:
            count = 0
            for value in iter_jsonl(path):
                validate_instance(value, schema)
                count += 1
            print(f"Validated {count} JSONL records as {kind}")
        else:
            value = load_json(path)
            validate_instance(value, schema)
            print(f"Validated {path} as {kind}")
    except (ContractValidationError, ValueError, json.JSONDecodeError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_replay(kind: str, input_path: str, output_path: str) -> int:
    values = list(iter_jsonl(input_path))
    if kind == "sensor-frame":
        results = replay_sensor_frames(values)
    else:
        results = replay_model_inputs(values)
    write_jsonl(output_path, results)
    print(f"Wrote {len(results)} model outputs to {output_path}")
    return 0


def cmd_generate_samples(output_dir: str) -> int:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    suite_path = root / "scenario_suite.json"
    frames_path = root / "sensor_frames.jsonl"
    inputs_path = root / "model_inputs.jsonl"
    suite = build_scenario_suite()
    suite_path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_jsonl(frames_path, sample_sensor_frames())
    write_jsonl(inputs_path, [item["input"] for item in suite])
    print(f"Generated samples in {root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        return cmd_demo(args.json)
    if args.command == "validate":
        return cmd_validate(args.kind, args.path, args.jsonl)
    if args.command == "replay":
        return cmd_replay(args.kind, args.input, args.output)
    if args.command == "generate-samples":
        return cmd_generate_samples(args.output_dir)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
