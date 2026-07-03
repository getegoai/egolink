"""Build an offline KR-008 product-demo closed-loop report.

The report composes existing evidence instead of contacting hardware, the VPS,
or serial ports:

test-run export -> DATA-001 samples -> EALE-P0 evaluation
                + optional safety demo summary
                -> product-demo closed-loop report
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))

from scripts import evaluate_eale_p0_dataset as eale_evaluator
from scripts import export_location_fusion_dataset as dataset_exporter


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "product_demo"
REPORT_JSON = "product_demo_report.json"
REPORT_MARKDOWN = "product_demo_report.md"
GENERATOR_NAME = "build_product_demo_report"
GENERATOR_VERSION = "0.1.0-demo011"
REPORT_VERSION = "0.1.0"

FLOW_ORDER = [
    "user_trigger_or_safety_event",
    "device_location_status_request",
    "lte_raw_frame_uplink",
    "multi_source_evidence_aggregation",
    "eale_p0_location_belief",
    "user_confirmation_or_safety_rule",
    "report_export",
    "web_console_replay_review",
]

NON_CLAIMS = [
    "No product readiness claim.",
    "No emergency dispatch, calling, or SMS claim.",
    "No production fall-detection accuracy claim.",
    "No learned model or positioning accuracy claim.",
    "No long LTE stability, real reconnect recovery, or durable store-forward claim.",
    "No GNSS acceptance, battery/power, enclosure, camera, audio, or storage acceptance claim.",
]


class ProductDemoReportError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ProductDemoReportError(f"failed to read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProductDemoReportError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProductDemoReportError(f"JSON document must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def stable_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def status_rank(status: str) -> int:
    return {"pass": 0, "warn": 1, "not_run": 1, "fail": 2}.get(status, 2)


def overall_status(statuses: list[str]) -> str:
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status in {"warn", "not_run"} for status in statuses):
        return "warn"
    return "pass"


def flow_gate(
    status: str,
    summary: str,
    *,
    evidence: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    next_step: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": evidence or {},
        "warnings": warnings or [],
        "next_step": next_step,
    }


def web_review_gate_from_report(web_review_report: dict[str, Any] | None) -> dict[str, Any]:
    if not web_review_report:
        return flow_gate(
            "not_run",
            "Web console replay/review wiring is still pending for KR-008.",
            warnings=["web_console_product_demo_review_pending"],
            next_step="Run scripts/validate_product_demo_web_review.py and bind the report evidence.",
        )

    product_demo = as_dict(web_review_report.get("product_demo"))
    scope = as_dict(web_review_report.get("scope"))
    candidate = str(web_review_report.get("candidate") or product_demo.get("candidate") or "")
    result = str(web_review_report.get("result") or "").upper()
    errors: list[str] = []
    warnings: list[str] = []
    if web_review_report.get("tool") != "validate_product_demo_web_review":
        errors.append("web_review_tool_unrecognized")
    if result != "PASS":
        errors.append("web_review_gate_not_pass")
    if candidate != "KR-008 / DEMO-008 Product Demo Closed Loop":
        errors.append("web_review_candidate_mismatch")
    if scope.get("commands_sent") or scope.get("hardware_contacted") or scope.get("firmware_changed"):
        errors.append("web_review_scope_boundary_violated")
    if scope.get("gitlab_modified") or scope.get("kr008_promoted"):
        errors.append("web_review_release_boundary_violated")
    if product_demo.get("available") is not True:
        errors.append("web_review_product_demo_unavailable")

    warnings.extend(
        str(item)
        for item in as_list(web_review_report.get("warnings"))
        if item != "underlying_product_demo_web_flow_still_pending"
    )
    evidence = {
        "review_id": web_review_report.get("review_id"),
        "gate_version": web_review_report.get("gate_version"),
        "hub_url": web_review_report.get("hub_url"),
        "result": web_review_report.get("result"),
        "product_demo_status": product_demo.get("status"),
        "product_demo_ready_for_kr008_release": product_demo.get("ready_for_kr008_release"),
        "product_demo_evidence_mode": product_demo.get("evidence_mode"),
        "product_demo_test_run_id": product_demo.get("test_run_id"),
        "report_path": web_review_report.get("report_path"),
        "markdown_report_path": web_review_report.get("markdown_report_path"),
        "scope": scope,
    }
    if errors:
        return flow_gate(
            "fail",
            "Provided Web review gate evidence is not acceptable.",
            evidence=evidence,
            warnings=warnings,
            next_step="Rerun DEMO-010 and bind a passing Web review report.",
        )
    return flow_gate(
        "pass",
        "DEMO-010 Web/API review gate passed and is bound to this report.",
        evidence=evidence,
        warnings=warnings,
    )


def test_run_id_from_export(export: dict[str, Any]) -> str:
    test_run = as_dict(export.get("test_run"))
    return str(test_run.get("test_run_id") or export.get("test_run_id") or "unknown-test-run")


def first_sample(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return samples[0] if samples else {}


def sample_features(sample: dict[str, Any]) -> dict[str, Any]:
    return as_dict(sample.get("features"))


def sample_location_summary(sample: dict[str, Any]) -> dict[str, Any]:
    features = sample_features(sample)
    labels = as_dict(sample.get("labels"))
    belief = as_dict(features.get("location_belief"))
    gnss = as_dict(features.get("gnss"))
    return {
        "state": labels.get("location_state") or belief.get("state") or "Unknown",
        "confidence": labels.get("confidence") if labels.get("confidence") is not None else belief.get("confidence"),
        "label_source": labels.get("label_source"),
        "belief_source": belief.get("source"),
        "belief_reason": belief.get("reason"),
        "failure_modes": as_list(labels.get("failure_modes")),
        "gnss_fix": gnss.get("fix"),
        "gnss_state": gnss.get("state"),
        "lat_present": bool(gnss.get("lat_present")),
        "lon_present": bool(gnss.get("lon_present")),
    }


def feature_groups_present(sample: dict[str, Any]) -> list[str]:
    features = sample_features(sample)
    return sorted(key for key, value in features.items() if value not in (None, "", [], {}))


def has_lte_transport(samples: list[dict[str, Any]]) -> bool:
    for sample in samples:
        features = sample_features(sample)
        transport = as_dict(features.get("transport"))
        lte_http = as_dict(features.get("lte_http"))
        if transport.get("type") == "lte" or lte_http:
            return True
    return False


def raw_lineage_count(samples: list[dict[str, Any]]) -> int:
    total = 0
    for sample in samples:
        lineage = as_dict(sample.get("lineage"))
        total += len(as_list(lineage.get("raw_frame_refs")))
    return total


def derived_lineage_count(samples: list[dict[str, Any]]) -> int:
    total = 0
    for sample in samples:
        lineage = as_dict(sample.get("lineage"))
        total += len(as_list(lineage.get("derived_event_refs")))
    return total


def safety_event_counts(safety_summary: dict[str, Any]) -> dict[str, int]:
    counts = as_dict(safety_summary.get("event_counts"))
    return {str(key): int(value) for key, value in counts.items() if isinstance(value, int)}


def safety_stage_passed(safety_summary: dict[str, Any], stage: str) -> bool:
    return bool(as_dict(as_dict(safety_summary.get("stages")).get(stage)).get("passed"))


def build_safety_gates(safety_summary: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if not safety_summary:
        missing = flow_gate(
            "warn",
            "Safety trigger/user-confirmation evidence was not provided to this offline report.",
            warnings=["missing_safety_demo_summary"],
            next_step="Attach a full safety demo summary or Web safety-event record.",
        )
        return missing, missing

    counts = safety_event_counts(safety_summary)
    trigger_ok = bool(counts.get("motion_event") or counts.get("safety_event") or safety_stage_passed(safety_summary, "demo_v0_1"))
    confirmation_ok = bool(counts.get("user_confirmation") or counts.get("safety_event"))
    trigger_gate = flow_gate(
        "pass" if trigger_ok else "warn",
        "Safety trigger evidence is present." if trigger_ok else "Safety trigger evidence is incomplete.",
        evidence={
            "session_id": safety_summary.get("session_id"),
            "event_counts": counts,
            "demo_v0_1_passed": safety_stage_passed(safety_summary, "demo_v0_1"),
            "demo_v0_5_passed": safety_stage_passed(safety_summary, "demo_v0_5"),
        },
        warnings=[] if trigger_ok else ["missing_safety_trigger_or_stage_gate"],
    )
    decision_gate = flow_gate(
        "pass" if confirmation_ok else "warn",
        "User confirmation or safety-rule decision evidence is present."
        if confirmation_ok
        else "User confirmation or safety-rule decision evidence is incomplete.",
        evidence={
            "session_id": safety_summary.get("session_id"),
            "user_confirmation_count": counts.get("user_confirmation", 0),
            "safety_event_count": counts.get("safety_event", 0),
            "quality_report": as_dict(safety_summary.get("quality_report")),
            "replay_report": as_dict(safety_summary.get("replay_report")),
        },
        warnings=[] if confirmation_ok else ["missing_user_confirmation_or_safety_rule"],
    )
    return trigger_gate, decision_gate


def build_flow(
    *,
    samples: list[dict[str, Any]],
    manifest: dict[str, Any],
    eale_report: dict[str, Any],
    safety_summary: dict[str, Any] | None,
    web_review_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = as_dict(manifest.get("source"))
    commands = int(source.get("command_count") or 0)
    raw_frames = int(source.get("raw_frame_count") or 0)
    sample = first_sample(samples)
    location = sample_location_summary(sample)
    groups = feature_groups_present(sample)
    raw_refs = raw_lineage_count(samples)
    derived_refs = derived_lineage_count(samples)
    eale_status = str(as_dict(eale_report.get("result")).get("status") or "fail")

    trigger_gate, decision_gate = build_safety_gates(safety_summary)
    request_gate = flow_gate(
        "pass" if commands > 0 else "fail",
        "A device location/status request command is present."
        if commands > 0
        else "No command-scoped location/status request was found.",
        evidence={"command_count": commands, "sample_id": sample.get("sample_id")},
    )
    raw_gate = flow_gate(
        "pass" if raw_frames > 0 and raw_refs > 0 and has_lte_transport(samples) else "fail",
        "LTE raw-frame uplink evidence is linked to the observation window."
        if raw_frames > 0 and raw_refs > 0 and has_lte_transport(samples)
        else "LTE raw-frame uplink lineage is missing or not LTE-labelled.",
        evidence={
            "export_raw_frame_count": raw_frames,
            "sample_raw_frame_refs": raw_refs,
            "sample_derived_event_refs": derived_refs,
            "lte_transport_present": has_lte_transport(samples),
        },
    )
    multi_source_ok = len(set(groups).intersection({"gnss", "cell", "lte", "transport", "lte_http", "command"})) >= 3
    aggregation_gate = flow_gate(
        "pass" if multi_source_ok else "warn",
        "Multi-source evidence is aggregated into DATA-001 features."
        if multi_source_ok
        else "Evidence aggregation is present but thin.",
        evidence={"feature_groups": groups},
        warnings=[] if multi_source_ok else ["thin_multi_source_evidence"],
    )
    eale_gate = flow_gate(
        "pass" if eale_status != "fail" and bool(samples) else "fail",
        "EALE-P0 produced a reviewable location belief."
        if eale_status != "fail" and bool(samples)
        else "EALE-P0 could not produce a reviewable location belief.",
        evidence={
            "dataset_status": eale_status,
            "location": location,
            "training_ready": as_dict(eale_report.get("training_readiness")).get("model_training_ready"),
            "release_review_supported": as_dict(eale_report.get("release_gate_usage")).get("can_support_release_review"),
        },
        warnings=as_list(as_dict(eale_report.get("result")).get("warnings")),
    )
    report_gate = flow_gate(
        "pass",
        "This offline product-demo report was exported.",
        evidence={"report_json": REPORT_JSON, "report_markdown": REPORT_MARKDOWN},
    )
    web_gate = web_review_gate_from_report(web_review_report)

    return {
        "user_trigger_or_safety_event": trigger_gate,
        "device_location_status_request": request_gate,
        "lte_raw_frame_uplink": raw_gate,
        "multi_source_evidence_aggregation": aggregation_gate,
        "eale_p0_location_belief": eale_gate,
        "user_confirmation_or_safety_rule": decision_gate,
        "report_export": report_gate,
        "web_console_replay_review": web_gate,
    }


def build_product_demo_report(
    test_run_export: dict[str, Any],
    *,
    safety_summary: dict[str, Any] | None = None,
    web_review_report: dict[str, Any] | None = None,
    created_at: str | None = None,
    dataset_dir: Path | None = None,
    samples_path: Path | None = None,
    manifest_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    created_at = created_at or utc_now()
    samples, manifest = dataset_exporter.build_dataset(
        test_run_export,
        split_name="holdout",
        split_rule="product_demo_single_run_holdout",
        created_at=created_at,
    )
    eale_report = eale_evaluator.evaluate_dataset(
        samples,
        manifest,
        samples_path=samples_path,
        manifest_path=manifest_path,
        dataset_dir=dataset_dir,
        created_at=created_at,
    )
    flow = build_flow(
        samples=samples,
        manifest=manifest,
        eale_report=eale_report,
        safety_summary=safety_summary,
        web_review_report=web_review_report,
    )
    statuses = [as_dict(flow.get(step)).get("status", "fail") for step in FLOW_ORDER]
    flow_status = overall_status([str(item) for item in statuses])
    warnings: list[str] = []
    errors: list[str] = []
    for gate in flow.values():
        gate_dict = as_dict(gate)
        warnings.extend(str(item) for item in as_list(gate_dict.get("warnings")))
        if gate_dict.get("status") == "fail":
            errors.append(str(gate_dict.get("summary") or "flow gate failed"))
    eale_warnings = [str(item) for item in as_list(as_dict(eale_report.get("result")).get("warnings"))]
    warnings.extend(eale_warnings)
    test_run_id = test_run_id_from_export(test_run_export)
    safety_session_id = str(as_dict(safety_summary).get("session_id") or "") if safety_summary else ""
    evidence_mode = "single_run_or_unverified"
    if safety_summary and safety_session_id and safety_session_id != test_run_id:
        evidence_mode = "composite_existing_evidence"
        warnings.append("composite_evidence_not_same_run")
    elif safety_summary:
        evidence_mode = "single_run_evidence"

    sample = first_sample(samples)
    location = sample_location_summary(sample)
    web_review_source = as_dict(web_review_report) if web_review_report else {}
    web_review_bound = as_dict(flow.get("web_console_replay_review")).get("status") == "pass"
    if evidence_mode == "composite_existing_evidence":
        warnings.append("composite_evidence_not_same_run")
    if not as_dict(eale_report.get("training_readiness")).get("model_training_ready"):
        warnings.append("dataset_not_ready_for_model_training")
    if location.get("state") != "Fine":
        warnings.append("location_belief_not_fine")
    status = "fail" if errors else ("warn" if flow_status == "warn" or warnings else flow_status)
    release_blockers = release_blockers_for_report(
        errors=errors,
        warnings=warnings,
        location=location,
        web_review_bound=web_review_bound,
    )
    report = {
        "report_version": REPORT_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "created_at": created_at},
        "demo": {
            "candidate": "KR-008 / DEMO-008 Product Demo Closed Loop",
            "mode": "offline_evidence_composition",
            "hardware_contacted": False,
            "vps_contacted": False,
            "product_ready": False,
        },
        "source": {
            "test_run_id": test_run_id,
            "safety_session_id": safety_session_id or None,
            "evidence_mode": evidence_mode,
            "dataset_samples": len(samples),
            "dataset_manifest": as_dict(manifest.get("source")),
            "web_review": {
                "review_id": web_review_source.get("review_id"),
                "result": web_review_source.get("result"),
                "gate_version": web_review_source.get("gate_version"),
                "report_path": web_review_source.get("report_path"),
                "markdown_report_path": web_review_source.get("markdown_report_path"),
            }
            if web_review_source
            else None,
        },
        "result": {
            "status": status,
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
            "ready_for_kr008_release": False,
            "why_not_release_ready": release_blockers,
        },
        "flow_order": FLOW_ORDER,
        "flow": flow,
        "location": location,
        "evidence_summary": {
            "flow_status_counts": stable_counts([str(status) for status in statuses]),
            "feature_groups": feature_groups_present(sample),
            "raw_frame_refs": raw_lineage_count(samples),
            "derived_event_refs": derived_lineage_count(samples),
            "dataset_result": as_dict(eale_report.get("result")),
            "dataset_counts": as_dict(eale_report.get("counts")),
            "training_readiness": as_dict(eale_report.get("training_readiness")),
            "release_gate_usage": as_dict(eale_report.get("release_gate_usage")),
            "web_review": {
                "bound": web_review_bound,
                "review_id": web_review_source.get("review_id") if web_review_source else None,
                "result": web_review_source.get("result") if web_review_source else None,
                "gate_version": web_review_source.get("gate_version") if web_review_source else None,
            },
        },
        "non_claims": NON_CLAIMS,
        "next_gates": [
            "Create a same-run product demo scenario or explicitly accept composite evidence.",
            "Bind a KR-008 manifest only after remaining release blockers are cleared.",
            "Keep real reconnect, durable store-forward, GNSS acceptance, battery/power, and enclosure gates separate.",
        ],
    }
    return report, samples, manifest, eale_report


def release_blockers_for_report(
    *,
    errors: list[str],
    warnings: list[str],
    location: dict[str, Any],
    web_review_bound: bool,
) -> list[str]:
    if errors:
        return ["one_or_more_required_flow_gates_failed"]
    blockers: list[str] = []
    warning_set = set(warnings)
    if "web_console_product_demo_review_pending" in warning_set or not web_review_bound:
        blockers.append("web_console_product_demo_review_pending")
    if "composite_evidence_not_same_run" in warning_set:
        blockers.append("same_run_product_demo_evidence_missing")
    if "dataset_not_ready_for_model_training" in warning_set:
        blockers.append("dataset_not_ready_for_model_training")
    if "location_belief_not_fine" in warning_set:
        blockers.append(f"location_belief_not_fine:{location.get('state', 'Unknown')}")
    blockers.append("kr008_manifest_not_created_or_promoted")
    return sorted(set(blockers))


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    result = as_dict(report.get("result"))
    source = as_dict(report.get("source"))
    location = as_dict(report.get("location"))
    evidence = as_dict(report.get("evidence_summary"))
    lines = [
        "# Product Demo Closed Loop Report",
        "",
        f"- Result: {result.get('status', 'unknown')}",
        f"- Candidate: {as_dict(report.get('demo')).get('candidate', 'unknown')}",
        f"- Test run: {source.get('test_run_id', 'unknown')}",
        f"- Safety session: {source.get('safety_session_id') or 'not provided'}",
        f"- Web review: {as_dict(as_dict(report.get('evidence_summary')).get('web_review')).get('result') or 'not bound'}",
        f"- Product ready: {as_dict(report.get('demo')).get('product_ready', False)}",
        "",
        "## Flow Gates",
        "",
        "| Step | Status | Summary |",
        "|---|---|---|",
    ]
    flow = as_dict(report.get("flow"))
    for step in FLOW_ORDER:
        gate = as_dict(flow.get(step))
        lines.append(f"| `{step}` | {gate.get('status', 'unknown')} | {gate.get('summary', '')} |")
    lines.extend(
        [
            "",
            "## Location Belief",
            "",
            f"- State: {location.get('state', 'Unknown')}",
            f"- Confidence: {location.get('confidence')}",
            f"- Reason: {location.get('belief_reason') or location.get('failure_modes') or 'unknown'}",
            f"- GNSS: fix={location.get('gnss_fix')} state={location.get('gnss_state')}",
            "",
            "## Evidence",
            "",
            f"- Feature groups: {json.dumps(evidence.get('feature_groups', []), sort_keys=True)}",
            f"- Raw frame refs: {evidence.get('raw_frame_refs', 0)}",
            f"- Derived event refs: {evidence.get('derived_event_refs', 0)}",
            f"- Training readiness: {json.dumps(evidence.get('training_readiness', {}), sort_keys=True)}",
            "",
            "## Warnings",
            "",
        ]
    )
    warnings = as_list(result.get("warnings"))
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    errors = as_list(result.get("errors"))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    blockers = as_list(result.get("why_not_release_ready"))
    lines.extend(["", "## Release Blockers", ""])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Non-Claims", ""])
    lines.extend(f"- {item}" for item in as_list(report.get("non_claims")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(
    output_dir: Path,
    report: dict[str, Any],
    samples: list[dict[str, Any]],
    manifest: dict[str, Any],
    eale_report: dict[str, Any],
) -> dict[str, Path]:
    dataset_dir = output_dir / "location_dataset"
    samples_path = dataset_dir / "samples.jsonl"
    manifest_path = dataset_dir / "manifest.json"
    eale_json = dataset_dir / eale_evaluator.REPORT_JSON
    eale_md = dataset_dir / eale_evaluator.REPORT_MARKDOWN
    report_json = output_dir / REPORT_JSON
    report_md = output_dir / REPORT_MARKDOWN
    write_jsonl(samples_path, samples)
    write_json(manifest_path, manifest)
    write_json(eale_json, eale_report)
    eale_evaluator.write_markdown(eale_md, eale_report)
    report_with_paths = dict(report)
    report_with_paths["paths"] = {
        "product_demo_report_json": str(report_json),
        "product_demo_report_markdown": str(report_md),
        "dataset_samples": str(samples_path),
        "dataset_manifest": str(manifest_path),
        "eale_report_json": str(eale_json),
        "eale_report_markdown": str(eale_md),
    }
    write_json(report_json, report_with_paths)
    write_markdown(report_md, report_with_paths)
    return {
        "product_demo_report_json": report_json,
        "product_demo_report_markdown": report_md,
        "dataset_samples": samples_path,
        "dataset_manifest": manifest_path,
        "eale_report_json": eale_json,
        "eale_report_markdown": eale_md,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-run-export", "--input", dest="test_run_export", type=Path, required=True)
    parser.add_argument("--safety-demo-summary", type=Path)
    parser.add_argument("--web-review-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        export = load_json(args.test_run_export)
        safety_summary = load_json(args.safety_demo_summary) if args.safety_demo_summary else None
        web_review_report = load_json(args.web_review_report) if args.web_review_report else None
        test_run_id = test_run_id_from_export(export)
        output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / test_run_id
        dataset_dir = output_dir / "location_dataset"
        samples_path = dataset_dir / "samples.jsonl"
        manifest_path = dataset_dir / "manifest.json"
        report, samples, manifest, eale_report = build_product_demo_report(
            export,
            safety_summary=safety_summary,
            web_review_report=web_review_report,
            created_at=args.created_at,
            dataset_dir=dataset_dir,
            samples_path=samples_path,
            manifest_path=manifest_path,
        )
        paths = write_outputs(output_dir, report, samples, manifest, eale_report)
    except ProductDemoReportError as exc:
        print(f"FAIL product demo report: {exc}", file=sys.stderr)
        return 1

    status = as_dict(report.get("result")).get("status", "fail")
    if args.json:
        emitted = dict(report)
        emitted["paths"] = {key: str(value) for key, value in paths.items()}
        print(json.dumps(emitted, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{str(status).upper()} product demo report={paths['product_demo_report_json']}")
    return 0 if status != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
