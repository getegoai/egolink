"""Validate the D1 Link Through Web/API surface.

This is a no-hardware read-only gate for the D1 demo. It checks that the
Message Hub and Dashboard expose the D1 location estimate, upload metrics, and
power-curve entry points. A PASS means the Web/API surface is ready to review
available D1 evidence; it is not a location-accuracy, battery-life, or hardware
acceptance claim.
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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "d1_web_api"
GATE_VERSION = "D1.web_api.v1"
DASHBOARD_MARKERS = (
    "D1 Link Through",
    "d1LinkPanel",
    "Upload Success",
    "Location Uploads",
    "Power Curve",
    "data-d1-map-mode",
    "data-map-review-mode",
    "data-map-provider-mode",
    "map-track",
    "Track points",
    "No-key Local Map",
    "Provider Status",
    "D2 Reference",
    "D1 Acceptance Gate",
    "d1AcceptanceBadge",
)


class D1WebApiValidationError(RuntimeError):
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
        raise D1WebApiValidationError(f"GET {path} returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise D1WebApiValidationError(f"GET {path} failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise D1WebApiValidationError(f"GET {path} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise D1WebApiValidationError(f"GET {path} must return a JSON object")
    return payload


def fetch_text(base_url: str, path: str, *, token: str | None, timeout: float) -> str:
    req = request.Request(base_url.rstrip("/") + path, headers=auth_headers(token), method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise D1WebApiValidationError(f"GET {path} returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise D1WebApiValidationError(f"GET {path} failed: {exc}") from exc


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


def dashboard_gate(html: str, *, markers: Iterable[str] = DASHBOARD_MARKERS) -> dict[str, Any]:
    missing = [marker for marker in markers if marker not in html]
    if missing:
        return gate(
            "G2_DASHBOARD_HTML",
            "FAIL",
            "Dashboard HTML is missing required D1 markers.",
            errors=["dashboard_d1_markers_missing"],
            evidence={"missing_markers": missing},
        )
    return gate(
        "G2_DASHBOARD_HTML",
        "PASS",
        "Dashboard HTML contains the D1 Link Through panel markers.",
        evidence={"markers": list(markers), "html_bytes": len(html.encode("utf-8"))},
    )


def select_d1_device(state: dict[str, Any], device_id: str | None = None) -> dict[str, Any]:
    devices = [item for item in as_list(state.get("devices")) if isinstance(item, dict)]
    for device in devices:
        if device_id and device.get("device_id") != device_id:
            continue
        if as_dict(device.get("d1_link")):
            return device
    return {}


def d1_state_gate(device: dict[str, Any]) -> dict[str, Any]:
    d1 = as_dict(device.get("d1_link"))
    acceptance = as_dict(d1.get("acceptance_gate"))
    estimate = as_dict(d1.get("location_estimate"))
    map_surface = as_dict(d1.get("map_surface"))
    provider = as_dict(map_surface.get("provider"))
    privacy = as_dict(map_surface.get("privacy"))
    trajectory = as_dict(map_surface.get("trajectory"))
    points = as_list(map_surface.get("points"))
    freshness = as_dict(d1.get("upload_freshness"))
    non_claims = set(str(item) for item in as_list(d1.get("non_claims")))
    errors: list[str] = []
    if not device:
        errors.append("d1_device_missing")
    if not acceptance.get("status"):
        errors.append("d1_acceptance_gate_missing")
    if estimate.get("available") is not True:
        errors.append("d1_location_estimate_not_available")
    if map_surface.get("visible") is not True:
        errors.append("d1_map_surface_not_visible")
    if len(points) < 2:
        errors.append("d1_map_trajectory_points_missing")
    if int(trajectory.get("point_count") or 0) < 2:
        errors.append("d1_map_trajectory_missing")
    if map_surface.get("accuracy_claim") != "none":
        errors.append("d1_map_surface_must_not_claim_accuracy")
    if provider.get("blocking_d1") is True:
        errors.append("d1_map_provider_must_not_block_d1")
    if provider.get("mode") in (None, ""):
        errors.append("d1_map_provider_mode_missing")
    if privacy.get("static_report_policy") != "bounded_summary_no_raw_coordinates":
        errors.append("d1_map_static_report_policy_not_bounded")
    if not freshness.get("last_location_upload_at"):
        errors.append("d1_location_upload_freshness_missing")
    for claim in ("location_accuracy_not_claimed", "battery_life_not_claimed"):
        if claim not in non_claims:
            errors.append(f"d1_non_claim_missing_{claim}")
    if errors:
        return gate(
            "G3_D1_STATE",
            "FAIL",
            "/api/state does not expose a complete D1 acceptance/location-estimate surface.",
            errors=errors,
            evidence=summarize_d1_device(device),
        )
    return gate(
        "G3_D1_STATE",
        "PASS",
        "/api/state exposes the D1 gate, local map evidence, freshness, provider non-blocking, and non-claim boundaries.",
        evidence=summarize_d1_device(device),
    )


def d1_metrics_gate(device: dict[str, Any]) -> dict[str, Any]:
    d1 = as_dict(device.get("d1_link"))
    uplink = as_dict(d1.get("uplink_metrics"))
    power = as_dict(d1.get("power_curve"))
    errors: list[str] = []
    warnings: list[str] = []
    if int(uplink.get("location_event_count") or 0) < 1:
        errors.append("d1_location_upload_count_missing")
    if int(power.get("sample_count") or 0) < 1:
        errors.append("d1_power_sample_count_missing")
    attempts = uplink.get("raw_post_attempt_count")
    successes = uplink.get("raw_post_success_count")
    failures = uplink.get("raw_post_failure_count")
    if attempts is None:
        warnings.append("d1_raw_post_counters_missing_using_server_received_events")
    elif int(attempts) < int(successes or 0) + int(failures or 0):
        errors.append("d1_raw_post_counters_inconsistent")
    if power.get("battery_life_claim") != "none":
        errors.append("d1_power_curve_must_not_claim_battery_life")
    if errors:
        return gate(
            "G4_D1_METRICS",
            "FAIL",
            "D1 upload/power metrics are missing or inconsistent.",
            errors=errors,
            warnings=warnings,
            evidence={"uplink_metrics": uplink, "power_curve": summarize_power_curve(power)},
        )
    return gate(
        "G4_D1_METRICS",
        "PASS",
        "D1 upload metrics and power-curve entry point are visible.",
        warnings=warnings,
        evidence={"uplink_metrics": uplink, "power_curve": summarize_power_curve(power)},
    )


def d1_evidence_gate(device: dict[str, Any]) -> dict[str, Any]:
    components = as_dict(as_dict(as_dict(device.get("d1_link")).get("evidence")).get("components"))
    errors = [
        f"d1_{name}_evidence_missing"
        for name in ("gnss", "cell_lte", "imu", "power")
        if as_dict(components.get(name)).get("seen") is not True
    ]
    if errors:
        return gate(
            "G5_D1_EVIDENCE_COMPONENTS",
            "FAIL",
            "D1 does not expose all required evidence component states.",
            errors=errors,
            evidence={"components": components},
        )
    return gate(
        "G5_D1_EVIDENCE_COMPONENTS",
        "PASS",
        "D1 exposes GNSS, Cell/LTE, IMU, and Power evidence component states.",
        evidence={"components": components},
    )


def summarize_power_curve(power: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_count": power.get("sample_count"),
        "first_sample_at": power.get("first_sample_at"),
        "latest_sample_at": power.get("latest_sample_at"),
        "window_s": power.get("window_s"),
        "delta_battery_mv": power.get("delta_battery_mv"),
        "delta_soc_pct": power.get("delta_soc_pct"),
        "battery_life_claim": power.get("battery_life_claim"),
    }


def summarize_d1_device(device: dict[str, Any]) -> dict[str, Any]:
    d1 = as_dict(device.get("d1_link"))
    return {
        "device_id": device.get("device_id"),
        "status": d1.get("status"),
        "acceptance_gate": d1.get("acceptance_gate"),
        "location_estimate": d1.get("location_estimate"),
        "map_surface": d1.get("map_surface"),
        "upload_freshness": d1.get("upload_freshness"),
        "uplink_metrics": d1.get("uplink_metrics"),
        "power_curve": summarize_power_curve(as_dict(d1.get("power_curve"))),
        "non_claims": d1.get("non_claims"),
    }


def evaluate_d1_web_api(
    *,
    health: dict[str, Any],
    state: dict[str, Any],
    dashboard_html: str,
    hub_url: str,
    review_id: str,
    device_id: str | None = None,
) -> dict[str, Any]:
    device = select_d1_device(state, device_id=device_id)
    gates = [
        health_gate(health),
        dashboard_gate(dashboard_html),
        d1_state_gate(device),
        d1_metrics_gate(device),
        d1_evidence_gate(device),
    ]
    result = result_from_gates(gates)
    return {
        "tool": "validate_d1_web_api",
        "gate_version": GATE_VERSION,
        "result": result,
        "created_at": utc_now(),
        "review_id": review_id,
        "hub_url": hub_url.rstrip("/"),
        "demo": "D1",
        "device_id": device.get("device_id") or device_id,
        "d1": summarize_d1_device(device),
        "gates": gates,
        "errors": collect_gate_messages(gates, "errors"),
        "warnings": collect_gate_messages(gates, "warnings"),
        "scope": {
            "hardware_contacted": False,
            "firmware_changed": False,
            "commands_sent": False,
            "gitlab_modified": False,
            "location_accuracy_claimed": False,
            "battery_life_claimed": False,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    d1 = as_dict(report.get("d1"))
    power = as_dict(d1.get("power_curve"))
    uplink = as_dict(d1.get("uplink_metrics"))
    map_surface = as_dict(d1.get("map_surface"))
    provider = as_dict(map_surface.get("provider"))
    trajectory = as_dict(map_surface.get("trajectory"))
    coord = as_dict(map_surface.get("coordinate_diagnostics"))
    lines = [
        "# D1 Web/API Review Gate",
        "",
        f"- Result: {report.get('result')}",
        f"- Gate version: {report.get('gate_version')}",
        f"- Review ID: {report.get('review_id')}",
        f"- Hub: {report.get('hub_url')}",
        f"- Device: {report.get('device_id')}",
        f"- D1 status: {d1.get('status')}",
        f"- D1 gate: {as_dict(d1.get('acceptance_gate')).get('status')}",
        f"- Location uploads: {uplink.get('location_event_count')}",
        f"- Map points: {trajectory.get('point_count')}",
        f"- Map review mode: {map_surface.get('review_mode')} / provider {provider.get('status')}",
        f"- Map accuracy claim: {map_surface.get('accuracy_claim')}",
        f"- Coordinate uploads: {coord.get('coordinate_event_count')} / {coord.get('location_event_count')} events; missing {coord.get('missing_coordinate_event_count')}",
        f"- Latest coordinate missing reason: {coord.get('latest_missing_reason')}",
        f"- Raw POST: {uplink.get('raw_post_success_count')} ok / {uplink.get('raw_post_failure_count')} fail / {uplink.get('raw_post_attempt_count')} attempts",
        f"- Power samples: {power.get('sample_count')}",
        f"- Power delta: {power.get('delta_battery_mv')} mV / {power.get('delta_soc_pct')}%",
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
            "- This gate validates D1 Web/API reviewability only.",
            "- It does not contact hardware, flash firmware, send commands, modify GitLab, claim location accuracy, or claim battery life.",
            "- A PASS still requires operator-recorded hardware evidence for the battery-powered 4G-board D1 run.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_d1_web_api_gate(
    *,
    hub_url: str,
    token: str | None,
    output_dir: Path,
    review_id: str,
    device_id: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    health = fetch_json(hub_url, "/health", token=token, timeout=timeout)
    state = fetch_json(hub_url, "/api/state", token=token, timeout=timeout)
    dashboard_html = fetch_text(hub_url, "/engineering", token=token, timeout=timeout)
    report = evaluate_d1_web_api(
        health=health,
        state=state,
        dashboard_html=dashboard_html,
        hub_url=hub_url,
        review_id=review_id,
        device_id=device_id,
    )
    report_json = output_dir / "d1_web_api_report.json"
    report_md = output_dir / "d1_web_api_report.md"
    report["report_path"] = str(report_json)
    report["markdown_report_path"] = str(report_md)
    write_json(report_json, report)
    write_markdown_report(report_md, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-url", default=DEFAULT_HUB_URL)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--review-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device-id")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    review_id = args.review_id or f"d1-web-api-{compact_utc_now()}"
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / review_id)
    report = run_d1_web_api_gate(
        hub_url=args.hub_url,
        token=read_token(args.token_file),
        output_dir=output_dir,
        review_id=review_id,
        device_id=args.device_id,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} D1 Web/API review: {report['markdown_report_path']}")
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
