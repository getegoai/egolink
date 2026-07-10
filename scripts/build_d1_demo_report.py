"""Build a one-page D1 demo evidence report from existing gate reports.

This script is offline-only. It does not contact hardware, send Message Hub
commands, flash firmware, or claim location accuracy or battery life.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_demo"
REPORT_JSON = "d1_demo_report.json"
REPORT_MARKDOWN = "d1_demo_report.md"
REPORT_VERSION = "D1.demo_report.v1"


class D1DemoReportError(RuntimeError):
    """Raised when required report inputs are missing or invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def numeric_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise D1DemoReportError(f"failed to read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise D1DemoReportError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise D1DemoReportError(f"JSON document must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def gate(
    gate_id: str,
    status: str,
    summary: str,
    *,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": status,
        "summary": summary,
        "errors": errors or [],
        "warnings": warnings or [],
        "evidence": evidence or {},
    }


def result_from_gates(gates: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "FAIL" for item in gates):
        return "FAIL"
    if any(item.get("status") == "WARN" for item in gates):
        return "WARN"
    return "PASS"


def web_api_gate(web_report: dict[str, Any]) -> dict[str, Any]:
    result = str(web_report.get("result") or "unknown").upper()
    scope = as_dict(web_report.get("scope"))
    errors: list[str] = []
    warnings: list[str] = []
    if result != "PASS":
        errors.append("d1_web_api_report_not_pass")
    for field in ("commands_sent", "firmware_changed", "gitlab_modified", "location_accuracy_claimed", "battery_life_claimed"):
        if scope.get(field) is True:
            errors.append(f"d1_web_api_scope_invalid_{field}")
    if scope.get("hardware_contacted") is True:
        warnings.append("d1_web_api_report_contacted_hardware")
    return gate(
        "G1_D1_WEB_API",
        "FAIL" if errors else "PASS",
        "D1 Web/API gate is passing and keeps review boundaries explicit.",
        errors=errors,
        warnings=warnings,
        evidence={
            "result": result,
            "report_path": web_report.get("report_path"),
            "device_id": web_report.get("device_id"),
            "d1_status": as_dict(web_report.get("d1")).get("status"),
        },
    )


def power_report_gate(power_report: dict[str, Any] | None) -> dict[str, Any]:
    if power_report is None:
        return gate(
            "G2_PWR001_POWER_REPORT",
            "WARN",
            "PWR-001 power report is not supplied yet.",
            warnings=["pwr001_power_report_missing"],
        )
    result = as_dict(power_report.get("result"))
    counts = as_dict(power_report.get("counts"))
    estimate = as_dict(power_report.get("consumption_estimate"))
    target = as_dict(power_report.get("target_comparison"))
    report_status = str(result.get("status") or "unknown").upper()
    errors: list[str] = []
    warnings: list[str] = []
    if report_status == "FAIL":
        errors.append("pwr001_power_report_failed")
    elif report_status != "PASS":
        warnings.append("pwr001_power_report_warn")
    if int(counts.get("measured_power_samples") or 0) < 1:
        errors.append("pwr001_measured_power_samples_missing")
    if estimate.get("status") != "estimated":
        warnings.append("pwr001_average_current_not_estimated")
    if target.get("status") != "estimated":
        warnings.append("pwr001_48h_gap_not_estimated")
    return gate(
        "G2_PWR001_POWER_REPORT",
        "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "PWR-001 power report is available with measured power samples.",
        errors=errors,
        warnings=warnings,
        evidence={
            "result": report_status,
            "report_path": power_report.get("report_path"),
            "markdown_report_path": power_report.get("markdown_report_path"),
            "test_run_id": as_dict(power_report.get("source")).get("test_run_id"),
            "duration_hours": power_report.get("duration_hours"),
            "measured_power_samples": counts.get("measured_power_samples"),
            "average_current_ma": estimate.get("average_current_ma"),
            "gap_vs_target_ma": target.get("gap_vs_target_ma"),
            "battery_life_claim": "none",
        },
    )


def d1_snapshot(web_report: dict[str, Any]) -> dict[str, Any]:
    d1 = as_dict(web_report.get("d1"))
    return {
        "status": d1.get("status"),
        "location_estimate": d1.get("location_estimate"),
        "map_surface": d1.get("map_surface"),
        "upload_freshness": d1.get("upload_freshness"),
        "uplink_metrics": d1.get("uplink_metrics"),
        "power_curve": d1.get("power_curve"),
        "non_claims": d1.get("non_claims"),
    }


def evaluate_d1_demo_report(
    *,
    web_report: dict[str, Any],
    power_report: dict[str, Any] | None = None,
    report_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    gates = [web_api_gate(web_report), power_report_gate(power_report)]
    result = result_from_gates(gates)
    ready_for_founder_review = result == "PASS"
    power = as_dict(power_report)
    return {
        "tool": "build_d1_demo_report",
        "report_version": REPORT_VERSION,
        "report_id": report_id,
        "created_at": created_at or utc_now(),
        "demo": "D1",
        "result": result,
        "ready_for_founder_review": ready_for_founder_review,
        "d1": d1_snapshot(web_report),
        "power": {
            "available": bool(power_report),
            "result": as_dict(power.get("result")).get("status"),
            "counts": power.get("counts"),
            "duration_hours": power.get("duration_hours"),
            "consumption_estimate": power.get("consumption_estimate"),
            "target_comparison": power.get("target_comparison"),
        },
        "gates": gates,
        "boundaries": {
            "offline_existing_reports_only": True,
            "hardware_contacted": False,
            "commands_sent": False,
            "firmware_changed": False,
            "gitlab_modified": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
            "product_readiness_claimed": False,
        },
    }


def fmt_number(value: object, digits: int = 2) -> str:
    number = numeric_or_none(value)
    return "n/a" if number is None else f"{number:.{digits}f}"


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    d1 = as_dict(report.get("d1"))
    uplink = as_dict(d1.get("uplink_metrics"))
    power_curve = as_dict(d1.get("power_curve"))
    power = as_dict(report.get("power"))
    estimate = as_dict(power.get("consumption_estimate"))
    target = as_dict(power.get("target_comparison"))
    lines = [
        "# D1 Demo Evidence Report",
        "",
        f"- Result: {report.get('result')}",
        f"- Ready for founder review: {report.get('ready_for_founder_review')}",
        f"- Report ID: {report.get('report_id')}",
        f"- D1 status: {d1.get('status')}",
        f"- Map surface: {as_dict(d1.get('map_surface')).get('mode')}",
        f"- Location uploads: {uplink.get('location_event_count')}",
        f"- Raw POST: {uplink.get('raw_post_success_count')} ok / {uplink.get('raw_post_failure_count')} fail / {uplink.get('raw_post_attempt_count')} attempts",
        f"- D1 power samples: {power_curve.get('sample_count')}",
        f"- PWR-001 duration h: {fmt_number(power.get('duration_hours'), 3)}",
        f"- Average current estimate: {fmt_number(estimate.get('average_current_ma'))} mA",
        f"- 48h target gap: {fmt_number(target.get('gap_vs_target_ma'))} mA",
        "",
        "## Gates",
        "",
    ]
    for item in as_list(report.get("gates")):
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('id')}: {item.get('status')} - {item.get('summary')}")
        for warning in as_list(item.get("warnings")):
            lines.append(f"  - warning: {warning}")
        for err in as_list(item.get("errors")):
            lines.append(f"  - error: {err}")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- Existing report composition only; no hardware, command, firmware, or VPS/GitLab mutation.",
            "- D1 does not claim location accuracy, battery life, product readiness, GNSS acceptance, or 48h/7d runtime.",
            "- Founder-review readiness requires both D1 Web/API gate PASS and PWR-001 measured power report PASS.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_d1_demo_report(
    *,
    web_api_report_path: Path,
    power_curve_report_path: Path | None,
    output_dir: Path,
    report_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    web_report = load_json_object(web_api_report_path)
    power_report = load_json_object(power_curve_report_path) if power_curve_report_path else None
    report = evaluate_d1_demo_report(
        web_report=web_report,
        power_report=power_report,
        report_id=report_id,
        created_at=created_at,
    )
    json_path = output_dir / REPORT_JSON
    md_path = output_dir / REPORT_MARKDOWN
    report["source"] = {
        "web_api_report_path": str(web_api_report_path),
        "power_curve_report_path": str(power_curve_report_path) if power_curve_report_path else None,
    }
    report["report_path"] = str(json_path)
    report["markdown_report_path"] = str(md_path)
    write_json(json_path, report)
    write_markdown_report(md_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-api-report", required=True, type=Path)
    parser.add_argument("--power-curve-report", type=Path)
    parser.add_argument("--report-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_id = args.report_id or f"d1-demo-{compact_utc_now()}"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / report_id)
    try:
        report = build_d1_demo_report(
            web_api_report_path=args.web_api_report,
            power_curve_report_path=args.power_curve_report,
            output_dir=output_dir,
            report_id=report_id,
        )
    except D1DemoReportError as exc:
        print(f"FAIL D1 demo report: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} D1 demo report: {report['markdown_report_path']}")
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
