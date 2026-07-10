"""Evaluate the deterministic M0 router against the bundled scenario suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_lab.safety_companion.src.baseline_router import RuleRouter
from model_lab.safety_companion.src.scenario_generator import build_scenario_suite


def evaluate() -> dict:
    router = RuleRouter()
    cases = []
    passed = 0
    for scenario in build_scenario_suite():
        output = router.evaluate(scenario["input"])
        expected = scenario["expected"]
        checks = {
            "risk_type": output["risk_type"] == expected["risk_type"],
            "recommended_action": output["recommended_action"] == expected["recommended_action"],
            "priority": output["priority"] == expected["priority"],
            "privacy_evidence": not bool(set(expected.get("forbidden_evidence", [])) & set(output["evidence_request"])),
        }
        case_passed = all(checks.values())
        passed += int(case_passed)
        cases.append(
            {
                "id": scenario["id"],
                "passed": case_passed,
                "checks": checks,
                "expected": expected,
                "output": output,
            }
        )
    return {
        "model_name": router.config.model_name,
        "model_version": router.config.model_version,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "pass_rate": passed / len(cases) if cases else 0.0,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="optional JSON report path")
    args = parser.parse_args()
    report = evaluate()
    print(f"Safety Companion baseline: {report['passed']}/{report['total']} scenarios passed")
    for case in report["cases"]:
        print(f"  [{'PASS' if case['passed'] else 'FAIL'}] {case['id']}")
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report written to {path}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
