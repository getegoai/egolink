"""Analyze PWR-001 power telemetry from a Message Hub test-run export."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "power"
GENERATOR_NAME = "PWR-001.power_curve_analysis"
GENERATOR_VERSION = "0.1.0"
REPORT_JSON = "power_curve_report.json"
REPORT_MARKDOWN = "power_curve_report.md"


class PowerCurveError(RuntimeError):
    """Raised when a power export cannot be analyzed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def first_known(*values: object) -> object | None:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def numeric_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "null", "unknown", "nan"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise PowerCurveError(f"failed to read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PowerCurveError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PowerCurveError(f"JSON document must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_export_messages(export: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for index, message in enumerate(as_list(export.get("messages"))):
        if isinstance(message, dict):
            yield f"messages[{index}]", message
    for index, raw_frame in enumerate(as_list(export.get("raw_frames"))):
        if not isinstance(raw_frame, dict):
            continue
        derived = as_dict(as_dict(raw_frame.get("parse_result")).get("derived_message"))
        if derived:
            yield f"raw_frames[{index}].parse_result.derived_message", derived


def extract_power_sample(source_path: str, message: dict[str, Any]) -> dict[str, Any] | None:
    power = as_dict(message.get("power"))
    payload = as_dict(message.get("payload"))
    battery_mv = numeric_or_none(first_known(power.get("battery_mv"), message.get("battery_mv"), payload.get("battery_mv")))
    soc_pct = numeric_or_none(
        first_known(
            power.get("soc_pct"),
            power.get("battery_percent"),
            message.get("soc_pct"),
            message.get("battery_percent"),
            message.get("battery"),
            payload.get("battery"),
        )
    )
    charging = first_known(power.get("charging"), message.get("charging"), payload.get("charging"))
    source = first_known(power.get("source"), power.get("battery_source"), message.get("battery_source"), "unknown")
    source_status = first_known(power.get("source_status"), message.get("source_status"))
    evidence_status = first_known(power.get("evidence_status"), power.get("source_status"))
    state = first_known(power.get("state"), message.get("power_state"))
    timestamp = parse_timestamp(first_known(message.get("server_received_at"), message.get("ts"), message.get("timestamp")))
    if battery_mv is None and soc_pct is None and not power:
        return None
    return {
        "source_path": source_path,
        "timestamp": iso_or_none(timestamp),
        "timestamp_sort": timestamp.timestamp() if timestamp else None,
        "message_type": message.get("message_type"),
        "event_type": message.get("event_type"),
        "seq": message.get("seq"),
        "transport_type": first_known(as_dict(message.get("transport")).get("type"), message.get("transport_type")),
        "battery_mv": battery_mv,
        "soc_pct": soc_pct,
        "charging": charging,
        "source": source,
        "source_status": source_status,
        "evidence_status": evidence_status,
        "state": state,
    }


def collect_power_samples(export: dict[str, Any]) -> list[dict[str, Any]]:
    samples = [
        sample
        for source_path, message in iter_export_messages(export)
        for sample in [extract_power_sample(source_path, message)]
        if sample is not None
    ]
    return sorted(samples, key=lambda item: (item.get("timestamp_sort") is None, item.get("timestamp_sort") or 0.0, str(item.get("source_path"))))


def numeric_stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "first": None, "last": None, "delta": None, "mean": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "first": values[0],
        "last": values[-1],
        "delta": values[-1] - values[0],
        "mean": sum(values) / len(values),
    }


def duration_hours(samples: list[dict[str, Any]]) -> float | None:
    timestamps = [numeric_or_none(sample.get("timestamp_sort")) for sample in samples]
    timestamps = [item for item in timestamps if item is not None]
    if len(timestamps) < 2:
        return None
    return (max(timestamps) - min(timestamps)) / 3600.0


def build_consumption_estimate(samples: list[dict[str, Any]], battery_capacity_mah: float | None, hours: float | None) -> dict[str, Any]:
    soc_values = [float(sample["soc_pct"]) for sample in samples if sample.get("soc_pct") is not None]
    if not battery_capacity_mah:
        return {"status": "not_estimated", "reason": "battery_capacity_mah_not_provided"}
    if hours is None or hours <= 0:
        return {"status": "not_estimated", "reason": "duration_unavailable"}
    if len(soc_values) < 2:
        return {"status": "not_estimated", "reason": "soc_samples_unavailable"}
    soc_drop_pct = soc_values[0] - soc_values[-1]
    if soc_drop_pct <= 0:
        return {"status": "not_estimated", "reason": "soc_did_not_decrease"}
    used_mah = battery_capacity_mah * soc_drop_pct / 100.0
    return {
        "status": "estimated",
        "method": "soc_delta_over_elapsed_time",
        "battery_capacity_mah": battery_capacity_mah,
        "soc_drop_pct": soc_drop_pct,
        "used_mah": used_mah,
        "average_current_ma": used_mah / hours,
    }


def build_overlay(samples: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts = Counter(str(sample.get("event_type") or sample.get("message_type") or "unknown") for sample in samples)
    transport_counts = Counter(str(sample.get("transport_type") or "unknown") for sample in samples)
    state_counts = Counter(str(sample.get("state") or "unknown") for sample in samples)
    return {
        "event_counts": dict(sorted(event_counts.items())),
        "transport_counts": dict(sorted(transport_counts.items())),
        "power_state_counts": dict(sorted(state_counts.items())),
    }


def evaluate_power_curve(
    export: dict[str, Any],
    *,
    input_path: Path | None = None,
    created_at: str | None = None,
    min_duration_hours: float = 24.0,
    battery_capacity_mah: float | None = None,
) -> dict[str, Any]:
    samples = collect_power_samples(export)
    errors: list[str] = []
    warnings: list[str] = []
    if not samples:
        errors.append("export contains no power samples")
    hours = duration_hours(samples)
    if hours is None:
        warnings.append("fewer than two timestamped power samples; duration is unavailable")
    elif hours < min_duration_hours:
        warnings.append(f"duration {hours:.3f} h is below required {min_duration_hours:.3f} h")
    battery_values = [float(sample["battery_mv"]) for sample in samples if sample.get("battery_mv") is not None]
    soc_values = [float(sample["soc_pct"]) for sample in samples if sample.get("soc_pct") is not None]
    if not battery_values:
        warnings.append("no battery_mv samples available")
    if not soc_values:
        warnings.append("no soc_pct samples available")
    mock_samples = [sample for sample in samples if str(first_known(sample.get("source_status"), sample.get("evidence_status"), sample.get("source"))).lower() == "mock"]
    if mock_samples:
        warnings.append(f"{len(mock_samples)} samples are still marked mock")

    estimate = build_consumption_estimate(samples, battery_capacity_mah, hours)
    if estimate.get("status") != "estimated":
        warnings.append(f"average current not estimated: {estimate.get('reason')}")

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    test_run_id = first_known(as_dict(export.get("test_run")).get("test_run_id"), as_dict(export.get("test_run")).get("id"), "unknown-test-run")
    return {
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "created_at": created_at or utc_now()},
        "result": {"status": status, "errors": errors, "warnings": warnings},
        "source": {"test_run_id": test_run_id, "input_path": str(input_path) if input_path else None},
        "requirements": {"min_duration_hours": min_duration_hours, "battery_capacity_mah": battery_capacity_mah},
        "counts": {"samples": len(samples), "battery_mv_samples": len(battery_values), "soc_pct_samples": len(soc_values)},
        "duration_hours": hours,
        "battery_mv": numeric_stats(battery_values),
        "soc_pct": numeric_stats(soc_values),
        "transport_overlay": build_overlay(samples),
        "consumption_estimate": estimate,
        "samples": samples,
        "boundaries": [
            "Offline analysis over an existing Message Hub export.",
            "Average current is an engineering estimate only and requires battery capacity plus observed SoC drop.",
            "This report does not prove 48h or 7d product battery life.",
        ],
    }


def default_output_dir(report: dict[str, Any]) -> Path:
    test_run_id = str(as_dict(report.get("source")).get("test_run_id") or f"PWR-001-{datetime.now(timezone.utc):%Y%m%d}")
    return DEFAULT_OUTPUT_ROOT / test_run_id


def fmt_number(value: object, digits: int = 2) -> str:
    number = numeric_or_none(value)
    return "n/a" if number is None else f"{number:.{digits}f}"


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    result = as_dict(report.get("result"))
    source = as_dict(report.get("source"))
    estimate = as_dict(report.get("consumption_estimate"))
    lines = [
        "# PWR-001 Power Curve Report",
        "",
        f"- Result: {result.get('status', 'unknown')}",
        f"- Test run: {source.get('test_run_id', 'unknown')}",
        f"- Input export: {source.get('input_path', 'unknown')}",
        f"- Duration h: {fmt_number(report.get('duration_hours'), 3)}",
        f"- Battery mV first/last/min/max: {fmt_number(as_dict(report.get('battery_mv')).get('first'), 0)} / {fmt_number(as_dict(report.get('battery_mv')).get('last'), 0)} / {fmt_number(as_dict(report.get('battery_mv')).get('min'), 0)} / {fmt_number(as_dict(report.get('battery_mv')).get('max'), 0)}",
        f"- SoC first/last/delta pct: {fmt_number(as_dict(report.get('soc_pct')).get('first'))} / {fmt_number(as_dict(report.get('soc_pct')).get('last'))} / {fmt_number(as_dict(report.get('soc_pct')).get('delta'))}",
        f"- Average current estimate: {fmt_number(estimate.get('average_current_ma'))} mA ({estimate.get('status', 'not_estimated')})",
        "",
        "## Transport Overlay",
        "",
    ]
    overlay = as_dict(report.get("transport_overlay"))
    for name, payload in (("Events", overlay.get("event_counts")), ("Transport", overlay.get("transport_counts")), ("Power states", overlay.get("power_state_counts"))):
        lines.append(f"- {name}: {json.dumps(payload or {}, sort_keys=True)}")
    lines.extend(["", "## Warnings", ""])
    warnings = as_list(result.get("warnings"))
    lines.extend((f"- {warning}" for warning in warnings) if warnings else ["- none"])
    errors = as_list(result.get("errors"))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- {item}" for item in as_list(report.get("boundaries")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze_power_curve(
    *,
    input_path: Path,
    output_dir: Path | None = None,
    min_duration_hours: float = 24.0,
    battery_capacity_mah: float | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    export = load_json_object(input_path)
    report = evaluate_power_curve(
        export,
        input_path=input_path,
        created_at=created_at,
        min_duration_hours=min_duration_hours,
        battery_capacity_mah=battery_capacity_mah,
    )
    target_dir = output_dir or default_output_dir(report)
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / REPORT_JSON
    markdown_path = target_dir / REPORT_MARKDOWN
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    write_json(report_path, report)
    write_markdown_report(markdown_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "--export", dest="input_path", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--min-duration-hours", type=float, default=24.0)
    parser.add_argument("--battery-capacity-mah", type=float)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = analyze_power_curve(
            input_path=args.input_path,
            output_dir=args.output_dir,
            min_duration_hours=args.min_duration_hours,
            battery_capacity_mah=args.battery_capacity_mah,
        )
    except PowerCurveError as exc:
        print(f"FAIL PWR-001 power curve analysis: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        source = as_dict(report.get("source"))
        status = as_dict(report.get("result")).get("status")
        print(f"{status} PWR-001 power curve test_run={source.get('test_run_id')} report={report.get('markdown_report_path')}")
    return 1 if as_dict(report.get("result")).get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
