"""Validate the Product Demo Web/API review surface.

DEMO-010 is a no-hardware gate for the KR-008 product-demo path. It checks
that the current Message Hub exposes the latest product-demo report through
health, API state, the product-demo API, and Dashboard HTML. A PASS here means
the report is reviewable through Web/API; it does not promote KR-008 and does
not turn a composite WARN report into product readiness.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable
from urllib import error, request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_fw001_hw_loop import DEFAULT_HUB_URL, compact_utc_now, utc_now  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN_FILE = REPO_ROOT / "server" / "runtime" / "vps_message_hub_token.txt"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "product_demo_web_review"
EXPECTED_CANDIDATE = "KR-008 / DEMO-008 Product Demo Closed Loop"
GATE_VERSION = "DEMO-010.product_demo_web_review.v1"
DASHBOARD_MARKERS = ("Product Demo", "productDemoPanel", "KR-008", "DEMO-008")


class ProductDemoWebReviewError(RuntimeError):
    pass


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_text(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def read_token(token_file: Path | None) -> str | None:
    env_token = os.environ.get("EGOLINK_MESSAGE_HUB_TOKEN")
    if env_token:
        return env_token
    if token_file and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        return token or None
    return None


def auth_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def fetch_json(base_url: str, path: str, *, token: str | None, timeout: float) -> dict[str, Any]:
    req = request.Request(base_url.rstrip("/") + path, headers=auth_headers(token), method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProductDemoWebReviewError(f"GET {path} returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise ProductDemoWebReviewError(f"GET {path} failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProductDemoWebReviewError(f"GET {path} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProductDemoWebReviewError(f"GET {path} must return a JSON object")
    return payload


def fetch_text(base_url: str, path: str, *, token: str | None, timeout: float) -> str:
    req = request.Request(base_url.rstrip("/") + path, headers=auth_headers(token), method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProductDemoWebReviewError(f"GET {path} returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise ProductDemoWebReviewError(f"GET {path} failed: {exc}") from exc


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


def collect_gate_messages(gates: list[dict[str, Any]], key: str) -> list[str]:
    return unique_text(message for item in gates for message in as_list(item.get(key)))


def result_from_gates(gates: list[dict[str, Any]]) -> str:
    return "FAIL" if any(item.get("status") == "FAIL" for item in gates) else "PASS"


def health_gate(health: dict[str, Any]) -> dict[str, Any]:
    if health.get("ok") is True:
        return gate(
            "G1_HEALTH_ENDPOINT",
            "PASS",
            "Message Hub health endpoint is reachable.",
            evidence={"service": health.get("service"), "time": health.get("time")},
        )
    return gate(
        "G1_HEALTH_ENDPOINT",
        "FAIL",
        "Message Hub health endpoint did not return ok=true.",
        errors=["message_hub_health_not_ok"],
        evidence={"health": health},
    )


def product_demo_api_gate(
    demo: dict[str, Any],
    *,
    expected_candidate: str,
    allowed_statuses: set[str],
) -> dict[str, Any]:
    errors: list[str] = []
    if demo.get("available") is not True:
        errors.append("product_demo_report_not_available")
    if demo.get("candidate") != expected_candidate:
        errors.append("product_demo_candidate_mismatch")
    status = str(demo.get("status") or "")
    if status not in allowed_statuses:
        errors.append("product_demo_status_not_allowed")
    if not (demo.get("report_path") or as_dict(demo.get("paths")).get("product_demo_report_json")):
        errors.append("product_demo_report_path_missing")
    if errors:
        return gate(
            "G2_PRODUCT_DEMO_API",
            "FAIL",
            "Product Demo API does not expose the expected reviewable report.",
            errors=errors,
            evidence={
                "available": demo.get("available"),
                "candidate": demo.get("candidate"),
                "status": demo.get("status"),
                "report_path": demo.get("report_path"),
            },
        )
    return gate(
        "G2_PRODUCT_DEMO_API",
        "PASS",
        "Product Demo API exposes a bounded report summary.",
        evidence={
            "candidate": demo.get("candidate"),
            "status": demo.get("status"),
            "test_run_id": demo.get("test_run_id"),
            "evidence_mode": demo.get("evidence_mode"),
            "report_path": demo.get("report_path"),
            "markdown_path": demo.get("markdown_path"),
        },
    )


def state_consistency_gate(api_demo: dict[str, Any], state_demo: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for key in ("available", "candidate", "status", "test_run_id", "evidence_mode"):
        if state_demo.get(key) != api_demo.get(key):
            errors.append(f"product_demo_state_mismatch_{key}")
    if errors:
        return gate(
            "G3_STATE_API_CONSISTENCY",
            "FAIL",
            "/api/state product_demo summary does not match /api/v1/product-demo/latest.",
            errors=errors,
            evidence={"latest": summarize_demo(api_demo), "state": summarize_demo(state_demo)},
        )
    return gate(
        "G3_STATE_API_CONSISTENCY",
        "PASS",
        "/api/state carries the same Product Demo summary as the dedicated API.",
        evidence={"summary": summarize_demo(state_demo)},
    )


def dashboard_gate(html: str, *, markers: Iterable[str] = DASHBOARD_MARKERS) -> dict[str, Any]:
    missing = [marker for marker in markers if marker not in html]
    if missing:
        return gate(
            "G4_DASHBOARD_HTML",
            "FAIL",
            "Dashboard HTML is missing required Product Demo review markers.",
            errors=["dashboard_product_demo_markers_missing"],
            evidence={"missing_markers": missing},
        )
    return gate(
        "G4_DASHBOARD_HTML",
        "PASS",
        "Dashboard HTML contains the Product Demo review panel markers.",
        evidence={"markers": list(markers), "html_bytes": len(html.encode("utf-8"))},
    )


def release_boundary_gate(demo: dict[str, Any]) -> dict[str, Any]:
    status = str(demo.get("status") or "")
    ready = bool(demo.get("ready_for_kr008_release"))
    evidence_mode = str(demo.get("evidence_mode") or "")
    web_gate = as_dict(as_dict(demo.get("flow")).get("web_console_replay_review"))
    errors: list[str] = []
    warnings: list[str] = []

    if ready and status != "pass":
        errors.append("kr008_ready_true_with_non_pass_report")
    if ready and evidence_mode == "composite_existing_evidence":
        errors.append("kr008_ready_true_with_composite_evidence")
    if not ready:
        warnings.append("kr008_release_not_ready")
    if web_gate.get("status") in {"not_run", "warn"}:
        warnings.append("underlying_product_demo_web_flow_still_pending")
    if errors:
        return gate(
            "G5_RELEASE_BOUNDARY",
            "FAIL",
            "Product Demo release-readiness boundary is inconsistent.",
            errors=errors,
            warnings=warnings,
            evidence={
                "report_status": status,
                "ready_for_kr008_release": ready,
                "evidence_mode": evidence_mode,
                "web_console_replay_review": web_gate,
            },
        )
    return gate(
        "G5_RELEASE_BOUNDARY",
        "PASS",
        "Release boundary is explicit; this Web gate does not claim KR-008 readiness.",
        warnings=warnings,
        evidence={
            "report_status": status,
            "ready_for_kr008_release": ready,
            "evidence_mode": evidence_mode,
            "web_console_replay_review": web_gate,
            "why_not_release_ready": demo.get("why_not_release_ready"),
        },
    )


def summarize_demo(demo: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": demo.get("available"),
        "candidate": demo.get("candidate"),
        "status": demo.get("status"),
        "ready_for_kr008_release": demo.get("ready_for_kr008_release"),
        "evidence_mode": demo.get("evidence_mode"),
        "test_run_id": demo.get("test_run_id"),
        "safety_session_id": demo.get("safety_session_id"),
        "report_path": demo.get("report_path"),
        "markdown_path": demo.get("markdown_path"),
    }


def release_blockers(demo: dict[str, Any]) -> list[str]:
    return unique_text(
        [
            *as_list(demo.get("why_not_release_ready")),
            *as_list(demo.get("warnings")),
            *as_list(demo.get("errors")),
        ]
    )


def evaluate_product_demo_web_review(
    *,
    health: dict[str, Any],
    latest: dict[str, Any],
    state: dict[str, Any],
    dashboard_html: str,
    hub_url: str,
    review_id: str,
    expected_candidate: str = EXPECTED_CANDIDATE,
    allowed_statuses: set[str] | None = None,
) -> dict[str, Any]:
    allowed = allowed_statuses or {"pass", "warn"}
    api_demo = as_dict(latest.get("product_demo"))
    state_demo = as_dict(state.get("product_demo"))
    gates = [
        health_gate(health),
        product_demo_api_gate(api_demo, expected_candidate=expected_candidate, allowed_statuses=allowed),
        state_consistency_gate(api_demo, state_demo),
        dashboard_gate(dashboard_html),
        release_boundary_gate(api_demo),
    ]
    result = result_from_gates(gates)
    web_gate = as_dict(as_dict(api_demo.get("flow")).get("web_console_replay_review"))
    return {
        "tool": "validate_product_demo_web_review",
        "gate_version": GATE_VERSION,
        "result": result,
        "created_at": utc_now(),
        "review_id": review_id,
        "hub_url": hub_url.rstrip("/"),
        "candidate": api_demo.get("candidate"),
        "product_demo": {
            **summarize_demo(api_demo),
            "location": api_demo.get("location"),
            "flow_status_counts": api_demo.get("flow_status_counts"),
            "web_console_replay_review_status": web_gate.get("status"),
            "web_console_replay_review_summary": web_gate.get("summary"),
            "raw_frame_refs": api_demo.get("raw_frame_refs"),
            "derived_event_refs": api_demo.get("derived_event_refs"),
            "training_readiness": api_demo.get("training_readiness"),
        },
        "web_surface": {
            "health_ok": health.get("ok") is True,
            "latest_api_available": api_demo.get("available") is True,
            "state_api_available": state_demo.get("available") is True,
            "dashboard_html_markers": list(DASHBOARD_MARKERS),
        },
        "kr008_release_ready": bool(api_demo.get("ready_for_kr008_release")),
        "release_blockers": release_blockers(api_demo),
        "gates": gates,
        "errors": collect_gate_messages(gates, "errors"),
        "warnings": collect_gate_messages(gates, "warnings"),
        "scope": {
            "hardware_contacted": False,
            "firmware_changed": False,
            "commands_sent": False,
            "gitlab_modified": False,
            "kr008_promoted": False,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    demo = as_dict(report.get("product_demo"))
    lines = [
        "# Product Demo Web Review Gate",
        "",
        f"- Result: {report.get('result')}",
        f"- Gate version: {report.get('gate_version')}",
        f"- Review ID: {report.get('review_id')}",
        f"- Hub: {report.get('hub_url')}",
        f"- Candidate: {report.get('candidate')}",
        f"- Report status: {demo.get('status')}",
        f"- Evidence mode: {demo.get('evidence_mode')}",
        f"- Test run: {demo.get('test_run_id')}",
        f"- Safety session: {demo.get('safety_session_id')}",
        f"- Web flow in product report: {demo.get('web_console_replay_review_status')}",
        f"- KR-008 release ready: {report.get('kr008_release_ready')}",
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
    lines.extend(["", "## Release Blockers", ""])
    blockers = as_list(report.get("release_blockers"))
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This gate validates Web/API reviewability for the latest product-demo report.",
            "- It does not contact hardware, flash firmware, send commands, modify GitLab, or promote KR-008.",
            "- A PASS here can still carry KR-008 release blockers when the underlying report is WARN or composite.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_web_review_gate(
    *,
    hub_url: str,
    token: str | None,
    output_dir: Path,
    review_id: str,
    expected_candidate: str = EXPECTED_CANDIDATE,
    allowed_statuses: set[str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    health = fetch_json(hub_url, "/health", token=token, timeout=timeout)
    latest = fetch_json(hub_url, "/api/v1/product-demo/latest", token=token, timeout=timeout)
    state = fetch_json(hub_url, "/api/state", token=token, timeout=timeout)
    dashboard_html = fetch_text(hub_url, "/", token=token, timeout=timeout)
    report = evaluate_product_demo_web_review(
        health=health,
        latest=latest,
        state=state,
        dashboard_html=dashboard_html,
        hub_url=hub_url,
        review_id=review_id,
        expected_candidate=expected_candidate,
        allowed_statuses=allowed_statuses,
    )
    report_json = output_dir / "product_demo_web_review_report.json"
    report_md = output_dir / "product_demo_web_review_report.md"
    report["report_path"] = str(report_json)
    report["markdown_report_path"] = str(report_md)
    write_json(report_json, report)
    write_markdown_report(report_md, report)
    return report


def parse_statuses(value: str) -> set[str]:
    statuses = {item.strip().lower() for item in value.split(",") if item.strip()}
    if not statuses:
        raise argparse.ArgumentTypeError("allowed statuses must not be empty")
    return statuses


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-url", default=DEFAULT_HUB_URL)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--review-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-candidate", default=EXPECTED_CANDIDATE)
    parser.add_argument("--allowed-report-statuses", type=parse_statuses, default={"pass", "warn"})
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    review_id = args.review_id or f"product-demo-web-review-{compact_utc_now()}"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / review_id)
    report = run_web_review_gate(
        hub_url=args.hub_url,
        token=read_token(args.token_file),
        output_dir=output_dir,
        review_id=review_id,
        expected_candidate=args.expected_candidate,
        allowed_statuses=args.allowed_report_statuses,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} product demo web review: {report['markdown_report_path']}")
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
