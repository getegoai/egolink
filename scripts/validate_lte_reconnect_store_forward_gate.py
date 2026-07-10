"""Evaluate an offline LTE reconnect/store-forward gate from a test-run export.

LTE-010 is stricter than the LTE-005 reliability preflight. It does not accept
"fields are visible" as recovery proof. A PASS requires:

- LTE runtime evidence;
- a reconnect attempt with count/reason evidence;
- a concrete network failure reason;
- a later successful LTE ACK after the reconnect evidence;
- observed durable store-forward queue/counter evidence.

Missing reconnect or store-forward exercise is WARN, not FAIL. A claimed
reconnect or store-forward state without enough evidence is FAIL.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_lte_reliability_gate import (  # noqa: E402
    as_dict,
    as_list,
    collect_gate_messages,
    compact_utc_now,
    first_present,
    gate,
    int_or_none,
    load_export,
    nested_value,
    parse_timestamp,
    result_from_gates,
    runtime_records,
    unique_text,
    utc_now,
    write_json,
)


GATE_VERSION = "LTE-010.reconnect_store_forward.offline.v1"
DEFAULT_OUTPUT_ROOT = Path("reports") / "lte_reconnect_store_forward"
OK_REASON_CODES = {"", "none", "null", "ok", "lte_ready", "lte_http_ok", "ready"}
RECONNECT_STATES = {"reconnecting", "recovered", "ready_after_reconnect", "pdp_reactivate", "modem_reset"}
STORE_FORWARD_STATES = {"store_forward", "offline_queue", "durable_store_forward"}
VOLATILE_CACHE_STATES = {"volatile_outbox", "not_enabled", "disabled", "unknown", "unverified", "none"}


def text(value: object) -> str:
    return "" if value in (None, "") else str(value)


def normalized(value: object) -> str:
    return text(value).strip().lower()


def is_non_ok_reason(value: object) -> bool:
    return normalized(value) not in OK_REASON_CODES


def ordered_runtime_records(export: dict[str, Any]) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    for index, (source, record) in enumerate(runtime_records(export)):
        when = first_present(
            record.get("server_received_at"),
            record.get("updated_at"),
            record.get("created_at"),
            record.get("started_at"),
            record.get("completed_at"),
            record.get("ts"),
        )
        ordered.append(
            {
                "index": index,
                "source": source,
                "record": record,
                "timestamp": parse_timestamp(when),
            }
        )
    return ordered


def reliability_network(record: dict[str, Any]) -> dict[str, Any]:
    network = as_dict(as_dict(record.get("reliability")).get("network"))
    return {
        "mode": first_present(network.get("mode"), record.get("network_mode")),
        "state": first_present(network.get("state"), record.get("network_state")),
        "reconnect_count": first_present(network.get("reconnect_count"), record.get("network_reconnect_count")),
        "last_error": first_present(network.get("last_error"), record.get("network_last_error")),
        "last_reconnect_reason": first_present(
            network.get("last_reconnect_reason"),
            record.get("network_last_reconnect_reason"),
        ),
        "raw_post_failure_count": first_present(
            network.get("raw_post_failure_count"),
            record.get("network_raw_post_failure_count"),
        ),
    }


def reliability_cache(record: dict[str, Any]) -> dict[str, Any]:
    cache = as_dict(as_dict(record.get("reliability")).get("cache"))
    return {
        "state": first_present(cache.get("state"), record.get("cache_state")),
        "source_status": first_present(cache.get("source_status"), record.get("cache_source_status")),
        "queued_message_count": first_present(
            cache.get("queued_message_count"),
            record.get("cache_queued_message_count"),
        ),
        "dropped_message_count": first_present(
            cache.get("dropped_message_count"),
            record.get("cache_dropped_message_count"),
        ),
        "oldest_message_age_ms": first_present(
            cache.get("oldest_message_age_ms"),
            record.get("cache_oldest_message_age_ms"),
        ),
        "last_drop_reason": first_present(cache.get("last_drop_reason"), record.get("cache_last_drop_reason")),
        "retry_policy": first_present(cache.get("retry_policy"), record.get("cache_retry_policy")),
        "flush_attempt_count": first_present(cache.get("flush_attempt_count"), record.get("cache_flush_attempt_count")),
        "flush_success_count": first_present(cache.get("flush_success_count"), record.get("cache_flush_success_count")),
        "flush_failure_count": first_present(cache.get("flush_failure_count"), record.get("cache_flush_failure_count")),
    }


def lte_runtime_gate(export: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    raw_frames = 0
    for source, record in runtime_records(export):
        if source == "raw_frame":
            raw_frames += 1
        if nested_value(record, "transport.type") == "lte":
            records.append(
                {
                    "source": source,
                    "message_type": record.get("message_type"),
                    "event_type": record.get("event_type"),
                    "cmd_id": record.get("cmd_id"),
                    "seq": record.get("seq"),
                    "server_received_at": record.get("server_received_at"),
                }
            )
    if not records:
        return gate(
            "G1_LTE_RUNTIME_CHAIN",
            "FAIL",
            "No runtime record carries transport.type=lte.",
            errors=["lte_runtime_evidence_missing"],
        )
    status = "PASS" if raw_frames else "WARN"
    warnings = [] if raw_frames else ["raw_frame_evidence_missing"]
    return gate(
        "G1_LTE_RUNTIME_CHAIN",
        status,
        "LTE runtime evidence is visible.",
        warnings=warnings,
        evidence={"lte_record_count": len(records), "raw_frame_count": raw_frames, "sample_records": records[:5]},
    )


def reconnect_records(export: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in ordered_runtime_records(export):
        record = item["record"]
        network = reliability_network(record)
        reconnect_count = int_or_none(network.get("reconnect_count"))
        state = normalized(network.get("state"))
        reason = text(network.get("last_reconnect_reason"))
        last_error = text(network.get("last_error"))
        if reconnect_count and reconnect_count > 0 or reason or state in RECONNECT_STATES:
            hits.append(
                {
                    "index": item["index"],
                    "source": item["source"],
                    "timestamp": item["timestamp"].isoformat() if item["timestamp"] else None,
                    "message_type": record.get("message_type"),
                    "event_type": record.get("event_type"),
                    "cmd_id": record.get("cmd_id"),
                    "seq": record.get("seq"),
                    "reconnect_count": reconnect_count,
                    "last_reconnect_reason": reason or None,
                    "state": network.get("state"),
                    "last_error": last_error or None,
                }
            )
    return hits


def reconnect_attempt_gate(export: dict[str, Any]) -> dict[str, Any]:
    hits = reconnect_records(export)
    if not hits:
        return gate(
            "G2_RECONNECT_ATTEMPT_VISIBLE",
            "NOT_OBSERVED",
            "No reconnect attempt evidence is present in this export.",
            warnings=["reconnect_attempt_not_observed"],
        )
    incomplete = [item for item in hits if not item.get("reconnect_count") or not item.get("last_reconnect_reason")]
    if incomplete:
        return gate(
            "G2_RECONNECT_ATTEMPT_VISIBLE",
            "WARN",
            "Reconnect evidence is present but lacks count or reason detail.",
            warnings=["reconnect_count_or_reason_incomplete"],
            evidence={"reconnect_records": hits[:10], "incomplete": incomplete[:5]},
        )
    return gate(
        "G2_RECONNECT_ATTEMPT_VISIBLE",
        "PASS",
        "Reconnect attempt count and reason evidence are visible.",
        evidence={"reconnect_records": hits[:10]},
    )


def network_failure_records(export: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for item in ordered_runtime_records(export):
        record = item["record"]
        network = reliability_network(record)
        reason_candidates = [
            network.get("last_error"),
            nested_value(record, "transport.last_error"),
            nested_value(record, "lte_http.reason_code"),
            nested_value(record, "lte_http.poll_reason_code"),
            nested_value(record, "lte_http.error_code"),
            nested_value(record, "lte.reason_code"),
            nested_value(record, "cell.reason_code"),
        ]
        reasons = [text(value) for value in reason_candidates if is_non_ok_reason(value)]
        if reasons:
            failures.append(
                {
                    "index": item["index"],
                    "source": item["source"],
                    "timestamp": item["timestamp"].isoformat() if item["timestamp"] else None,
                    "message_type": record.get("message_type"),
                    "event_type": record.get("event_type"),
                    "cmd_id": record.get("cmd_id"),
                    "reasons": unique_text(reasons),
                }
            )
    return failures


def reconnect_failure_reason_gate(export: dict[str, Any]) -> dict[str, Any]:
    reconnect = reconnect_records(export)
    if not reconnect:
        return gate(
            "G3_RECONNECT_FAILURE_REASON",
            "NOT_OBSERVED",
            "Reconnect was not exercised, so no reconnect failure reason is required.",
            warnings=["reconnect_failure_not_observed"],
        )
    failures = network_failure_records(export)
    if not failures:
        return gate(
            "G3_RECONNECT_FAILURE_REASON",
            "WARN",
            "Reconnect was observed, but no concrete network/LTE/HTTP failure reason is visible.",
            warnings=["reconnect_failure_reason_missing"],
            evidence={"reconnect_records": reconnect[:10]},
        )
    return gate(
        "G3_RECONNECT_FAILURE_REASON",
        "PASS",
        "Reconnect/failure reason evidence is visible.",
        evidence={"failure_records": failures[:10]},
    )


def ack_ok_after(record: dict[str, Any]) -> bool:
    ack_status = first_present(record.get("status"), nested_value(record, "ack.status"))
    command_status = nested_value(record, "command.last_status")
    return (
        record.get("message_type") == "ack"
        and ack_status == "ok"
        and nested_value(record, "transport.type") == "lte"
        and (
            nested_value(record, "lte_http.poll_reason_code") in (None, "", "LTE_HTTP_OK")
            or nested_value(record, "lte_http.reason_code") in (None, "", "LTE_HTTP_OK")
        )
        and (command_status in (None, "", "ok") or as_dict(record.get("command")).get("parse_status"))
    )


def post_reconnect_recovery_gate(export: dict[str, Any]) -> dict[str, Any]:
    reconnect = reconnect_records(export)
    if not reconnect:
        return gate(
            "G4_POST_RECONNECT_RECOVERY",
            "NOT_OBSERVED",
            "Reconnect was not exercised, so no post-reconnect ACK can be proven.",
            warnings=["post_reconnect_ack_not_observed"],
        )
    first_reconnect_index = min(int(item["index"]) for item in reconnect)
    recovered: list[dict[str, Any]] = []
    for item in ordered_runtime_records(export):
        if int(item["index"]) <= first_reconnect_index:
            continue
        record = item["record"]
        if ack_ok_after(record):
            recovered.append(
                {
                    "index": item["index"],
                    "source": item["source"],
                    "timestamp": item["timestamp"].isoformat() if item["timestamp"] else None,
                    "cmd_id": record.get("cmd_id"),
                    "seq": record.get("seq"),
                    "status": record.get("status"),
                    "poll_reason_code": first_present(
                        nested_value(record, "lte_http.poll_reason_code"),
                        nested_value(record, "lte_http.reason_code"),
                    ),
                }
            )
    if not recovered:
        return gate(
            "G4_POST_RECONNECT_RECOVERY",
            "FAIL",
            "Reconnect was observed, but no later successful LTE ACK is present.",
            errors=["post_reconnect_lte_ack_missing"],
            evidence={"reconnect_records": reconnect[:10]},
        )
    return gate(
        "G4_POST_RECONNECT_RECOVERY",
        "PASS",
        "A later successful LTE ACK is visible after reconnect evidence.",
        evidence={"reconnect_records": reconnect[:5], "post_reconnect_acks": recovered[:5]},
    )


def store_forward_gate(export: dict[str, Any]) -> dict[str, Any]:
    store_forward_hits: list[dict[str, Any]] = []
    volatile_hits: list[dict[str, Any]] = []
    cache_hits: list[dict[str, Any]] = []
    for item in ordered_runtime_records(export):
        record = item["record"]
        cache = reliability_cache(record)
        state = normalized(cache.get("state"))
        if not any(value not in (None, "") for value in cache.values()):
            continue
        hit = {
            "index": item["index"],
            "source": item["source"],
            "timestamp": item["timestamp"].isoformat() if item["timestamp"] else None,
            "message_type": record.get("message_type"),
            "event_type": record.get("event_type"),
            "cmd_id": record.get("cmd_id"),
            "state": cache.get("state"),
            "source_status": cache.get("source_status"),
            "queued_message_count": int_or_none(cache.get("queued_message_count")),
            "dropped_message_count": int_or_none(cache.get("dropped_message_count")),
            "oldest_message_age_ms": int_or_none(cache.get("oldest_message_age_ms")),
            "last_drop_reason": cache.get("last_drop_reason"),
            "flush_attempt_count": int_or_none(cache.get("flush_attempt_count")),
            "flush_success_count": int_or_none(cache.get("flush_success_count")),
            "flush_failure_count": int_or_none(cache.get("flush_failure_count")),
        }
        cache_hits.append(hit)
        if state in STORE_FORWARD_STATES:
            store_forward_hits.append(hit)
        elif state in VOLATILE_CACHE_STATES or state:
            volatile_hits.append(hit)

    if not cache_hits:
        return gate(
            "G5_STORE_FORWARD_EVIDENCE",
            "WARN",
            "No cache/store-forward evidence is present.",
            warnings=["store_forward_not_observed"],
        )
    if not store_forward_hits:
        return gate(
            "G5_STORE_FORWARD_EVIDENCE",
            "WARN",
            "Cache evidence is visible, but it is not durable store-forward evidence.",
            warnings=["volatile_or_nonclaim_cache_only"],
            evidence={"cache_records": cache_hits[:10], "volatile_or_nonclaim_records": volatile_hits[:10]},
        )
    incomplete = [
        item
        for item in store_forward_hits
        if item.get("source_status") != "observed"
        or item.get("queued_message_count") is None
        or item.get("dropped_message_count") is None
        or item.get("oldest_message_age_ms") is None
    ]
    if incomplete:
        return gate(
            "G5_STORE_FORWARD_EVIDENCE",
            "FAIL",
            "Store-forward is claimed but queue/drop/age/source evidence is incomplete.",
            errors=["store_forward_evidence_incomplete"],
            evidence={"store_forward_records": store_forward_hits[:10], "incomplete": incomplete[:5]},
        )
    return gate(
        "G5_STORE_FORWARD_EVIDENCE",
        "PASS",
        "Observed store-forward queue/drop/age evidence is visible.",
        evidence={"store_forward_records": store_forward_hits[:10]},
    )


def evaluate_lte_reconnect_store_forward_export(
    export: dict[str, Any],
    *,
    input_path: Path | None = None,
) -> dict[str, Any]:
    test_run = as_dict(export.get("test_run"))
    gates = [
        lte_runtime_gate(export),
        reconnect_attempt_gate(export),
        reconnect_failure_reason_gate(export),
        post_reconnect_recovery_gate(export),
        store_forward_gate(export),
    ]
    result = result_from_gates(gates)
    firmware_versions = unique_text(
        first_present(record.get("fw_version"), nested_value(record, "ack.fw_version"))
        for _, record in runtime_records(export)
        if first_present(record.get("fw_version"), nested_value(record, "ack.fw_version")) not in (None, "")
    )
    return {
        "tool": "validate_lte_reconnect_store_forward_gate",
        "gate_version": GATE_VERSION,
        "result": result,
        "created_at": utc_now(),
        "input_path": str(input_path) if input_path else None,
        "test_run_id": test_run.get("test_run_id"),
        "task_id": test_run.get("task_id"),
        "device_id": test_run.get("device_id"),
        "board_id": test_run.get("board_id"),
        "connection_path": test_run.get("connection_path"),
        "firmware_versions": firmware_versions,
        "counts": {
            "messages": len(as_list(export.get("messages"))),
            "commands": len(as_list(export.get("commands"))),
            "raw_frames": len(as_list(export.get("raw_frames"))),
        },
        "gates": gates,
        "errors": collect_gate_messages(gates, "errors"),
        "warnings": collect_gate_messages(gates, "warnings"),
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# LTE-010 Reconnect Store-Forward Gate Report",
        "",
        f"- Result: {report.get('result')}",
        f"- Gate version: {report.get('gate_version')}",
        f"- Test run: {report.get('test_run_id')}",
        f"- Device: {report.get('device_id')}",
        f"- Board: {report.get('board_id')}",
        f"- Connection path: {report.get('connection_path')}",
        f"- Firmware versions: {', '.join(as_list(report.get('firmware_versions'))) or 'unknown'}",
        f"- Input: {report.get('input_path')}",
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
        for error in as_list(item.get("errors")):
            lines.append(f"  - error: {error}")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- This report is an offline evidence gate over an existing Message Hub export.",
            "- It does not flash firmware, contact hardware, send commands, or prove long LTE stability.",
            "- PASS requires a concrete reconnect event, post-reconnect ACK, and store-forward evidence.",
            "- WARN means the export is explainable but did not exercise the required behavior.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_output_dir(report: dict[str, Any]) -> Path:
    test_run_id = str(report.get("test_run_id") or f"lte010-{compact_utc_now()}")
    return DEFAULT_OUTPUT_ROOT / test_run_id


def validate_lte_reconnect_store_forward_gate(
    *,
    input_path: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    export = load_export(input_path)
    report = evaluate_lte_reconnect_store_forward_export(export, input_path=input_path)
    target_dir = output_dir or default_output_dir(report)
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / "lte_reconnect_store_forward_gate_report.json"
    markdown_path = target_dir / "lte_reconnect_store_forward_gate_report.md"
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    write_json(report_path, report)
    write_markdown_report(markdown_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to a Message Hub test_run_export.json file.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = validate_lte_reconnect_store_forward_gate(input_path=args.input, output_dir=args.output_dir)
    if args.json:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['result']} LTE-010 reconnect/store-forward gate: {report['markdown_report_path']}")
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
