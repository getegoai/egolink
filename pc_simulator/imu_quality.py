from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


REPORT_SCHEMA_VERSION = "egolink.imu_quality_report.v0.1"
QMI_TIMESTAMP_WRAP = 1 << 24


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
        if isinstance(message, dict):
            messages.append(message)
    return messages


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None, "stddev": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "stddev": pstdev(values) if len(values) > 1 else 0.0,
    }


def _gate(passed: bool, reason: str, **details: Any) -> dict[str, Any]:
    return {"passed": passed, "reason": reason, "details": details}


def _qmi_deltas(timestamps: list[int]) -> list[int]:
    deltas: list[int] = []
    for previous, current in zip(timestamps, timestamps[1:]):
        delta = current - previous
        if delta < 0:
            delta += QMI_TIMESTAMP_WRAP
        deltas.append(delta)
    return deltas


def _dominant_axis(mean_axes_mg: list[float]) -> dict[str, Any]:
    axis_names = ["x", "y", "z"]
    dominant_index = max(range(3), key=lambda index: abs(mean_axes_mg[index]))
    value = mean_axes_mg[dominant_index]
    return {
        "axis": axis_names[dominant_index],
        "sign": "positive" if value >= 0 else "negative",
        "mean_mg": value,
    }


def analyze_imu_messages(
    messages: list[dict[str, Any]],
    *,
    min_samples: int = 40,
    warmup_discard: int = 5,
    expected_whoami: int = 0x05,
    timing_tolerance_ratio: float = 0.25,
) -> dict[str, Any]:
    whoami_events = [message for message in messages if message.get("type") == "imu_whoami"]
    sample_events = [message for message in messages if message.get("type") == "imu_sample"]
    done_events = [message for message in messages if message.get("type") == "amoled_bridge_done"]

    whoami_payload = whoami_events[0].get("payload", {}) if whoami_events else {}
    done_payload = done_events[-1].get("payload", {}) if done_events else {}

    samples = []
    for event in sample_events:
        payload = event.get("payload", {})
        samples.append(
            {
                "seq": event.get("seq"),
                "sample_index": payload.get("sample_index"),
                "device_monotonic_ms": event.get("device_monotonic_ms"),
                "qmi_timestamp": payload.get("qmi_timestamp"),
                "accel_mg": payload.get("accel_mg"),
                "gyro_mdps": payload.get("gyro_mdps"),
                "source_availability": event.get("source_availability"),
                "source_status": event.get("source_status"),
            }
        )

    sample_indices = [
        sample["sample_index"]
        for sample in samples
        if isinstance(sample.get("sample_index"), int)
    ]
    expected_indices = set(range(min(sample_indices), max(sample_indices) + 1)) if sample_indices else set()
    missing_indices = sorted(expected_indices - set(sample_indices))
    duplicate_indices = sorted(
        index for index in set(sample_indices) if sample_indices.count(index) > 1
    )

    seq_values = [sample["seq"] for sample in samples if isinstance(sample.get("seq"), int)]
    expected_seq = set(range(min(seq_values), max(seq_values) + 1)) if seq_values else set()
    missing_seq = sorted(expected_seq - set(seq_values))

    monotonic_values = [
        sample["device_monotonic_ms"]
        for sample in samples
        if isinstance(sample.get("device_monotonic_ms"), (int, float))
    ]
    device_intervals = [
        float(current - previous)
        for previous, current in zip(monotonic_values, monotonic_values[1:])
    ]

    qmi_values = [
        sample["qmi_timestamp"]
        for sample in samples
        if isinstance(sample.get("qmi_timestamp"), int)
    ]
    qmi_intervals = _qmi_deltas(qmi_values)

    sample_hz_values = [
        event.get("sample_hz")
        for event in sample_events
        if isinstance(event.get("sample_hz"), (int, float)) and event.get("sample_hz") > 0
    ]
    expected_interval_ms = done_payload.get("sample_interval_ms")
    if not isinstance(expected_interval_ms, (int, float)) and sample_hz_values:
        expected_interval_ms = 1000.0 / float(sample_hz_values[0])
    if not isinstance(expected_interval_ms, (int, float)):
        expected_interval_ms = None

    observed_mean_interval = mean(device_intervals) if device_intervals else None
    observed_hz = 1000.0 / observed_mean_interval if observed_mean_interval else None
    timing_tolerance_ms = (
        float(expected_interval_ms) * timing_tolerance_ratio
        if isinstance(expected_interval_ms, (int, float))
        else None
    )
    timing_passed = bool(
        observed_mean_interval is not None
        and timing_tolerance_ms is not None
        and abs(observed_mean_interval - float(expected_interval_ms)) <= timing_tolerance_ms
    )

    warm_samples = samples[warmup_discard:] if len(samples) > warmup_discard else samples
    accel_vectors = [
        sample["accel_mg"]
        for sample in warm_samples
        if isinstance(sample.get("accel_mg"), list) and len(sample["accel_mg"]) == 3
    ]
    gyro_vectors = [
        sample["gyro_mdps"]
        for sample in warm_samples
        if isinstance(sample.get("gyro_mdps"), list) and len(sample["gyro_mdps"]) == 3
    ]

    accel_magnitudes = [
        math.sqrt(float(x) * float(x) + float(y) * float(y) + float(z) * float(z))
        for x, y, z in accel_vectors
    ]
    mean_axes_mg = [
        mean([float(vector[index]) for vector in accel_vectors]) if accel_vectors else 0.0
        for index in range(3)
    ]
    dominant_axis = _dominant_axis(mean_axes_mg)
    non_dominant_abs = [
        abs(value)
        for index, value in enumerate(mean_axes_mg)
        if ["x", "y", "z"][index] != dominant_axis["axis"]
    ]
    accel_mean_magnitude = mean(accel_magnitudes) if accel_magnitudes else None
    static_orientation_passed = bool(
        accel_mean_magnitude is not None
        and 850.0 <= accel_mean_magnitude <= 1150.0
        and abs(float(dominant_axis["mean_mg"])) >= 700.0
        and all(value <= 250.0 for value in non_dominant_abs)
    )

    gyro_abs_values = [
        abs(float(component))
        for vector in gyro_vectors
        for component in vector
    ]
    gyro_abs_mean = mean(gyro_abs_values) if gyro_abs_values else None
    gyro_static_passed = bool(gyro_abs_mean is not None and gyro_abs_mean <= 5000.0)

    source_availability_values = {sample.get("source_availability") for sample in samples}
    source_status_values = {sample.get("source_status") for sample in samples}
    source_boundary_passed = source_availability_values == {"bridge_uplink"} and source_status_values == {"unverified"}

    identity_passed = bool(
        whoami_payload.get("whoami") == expected_whoami
        and whoami_payload.get("whoami_expected") == expected_whoami
        and whoami_payload.get("axp2101_present") is True
    )
    completeness_passed = bool(
        len(samples) >= min_samples
        and not missing_indices
        and not duplicate_indices
        and not missing_seq
    )
    completion_passed = bool(
        done_payload.get("samples_emitted", len(samples)) == len(samples)
        and done_payload.get("read_errors", 0) == 0
        and done_payload.get("not_ready_count", 0) == 0
    )
    qmi_timestamp_passed = bool(qmi_intervals and all(delta > 0 for delta in qmi_intervals))

    gates = {
        "identity": _gate(identity_passed, "QMI8658 WHOAMI and AXP2101 identity"),
        "completeness": _gate(
            completeness_passed,
            "sample indices and event seq are contiguous",
            min_samples=min_samples,
            sample_count=len(samples),
            missing_indices=missing_indices,
            duplicate_indices=duplicate_indices,
            missing_seq=missing_seq,
        ),
        "completion": _gate(
            completion_passed,
            "firmware completion record reports no read/not-ready errors",
            done_payload=done_payload,
        ),
        "device_timing": _gate(
            timing_passed,
            "observed device interval matches requested sample interval",
            expected_interval_ms=expected_interval_ms,
            observed_mean_interval_ms=observed_mean_interval,
            tolerance_ms=timing_tolerance_ms,
            observed_hz=observed_hz,
        ),
        "qmi_timestamp": _gate(
            qmi_timestamp_passed,
            "QMI timestamp is monotonic across samples",
        ),
        "static_orientation": _gate(
            static_orientation_passed,
            "stationary accel vector is plausibly one dominant 1g axis",
            warmup_discard=warmup_discard,
            dominant_axis=dominant_axis,
            mean_accel_magnitude_mg=accel_mean_magnitude,
            mean_axes_mg=mean_axes_mg,
        ),
        "static_gyro": _gate(
            gyro_static_passed,
            "warm stationary gyro mean absolute rate is below sanity threshold",
            warmup_discard=warmup_discard,
            gyro_abs_mean_mdps=gyro_abs_mean,
        ),
        "source_boundary": _gate(
            source_boundary_passed,
            "source remains bridge_uplink/unverified until formal acceptance",
            source_availability_values=sorted(str(value) for value in source_availability_values),
            source_status_values=sorted(str(value) for value in source_status_values),
        ),
    }

    gate_failures = [name for name, gate in gates.items() if not gate["passed"]]
    formal_reasons = []
    if source_status_values == {"unverified"}:
        formal_reasons.append("source_status_unverified")
    if "device_timing" in gate_failures:
        formal_reasons.append("device_timing_gate_failed")
    if gate_failures:
        formal_reasons.append("quality_gates_not_all_passed")

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "message_counts": {
            "total": len(messages),
            "imu_whoami": len(whoami_events),
            "imu_sample": len(sample_events),
            "amoled_bridge_done": len(done_events),
        },
        "identity": {
            "axp2101_chip_id": whoami_payload.get("axp2101_chip_id"),
            "qmi8658_addr": whoami_payload.get("qmi8658_addr"),
            "whoami": whoami_payload.get("whoami"),
            "whoami_expected": whoami_payload.get("whoami_expected"),
            "revision": whoami_payload.get("revision"),
            "reset_result": whoami_payload.get("reset_result"),
        },
        "timing": {
            "expected_interval_ms": expected_interval_ms,
            "expected_sample_hz": sample_hz_values[0] if sample_hz_values else None,
            "observed_sample_hz": observed_hz,
            "device_interval_ms": _stats(device_intervals),
            "qmi_timestamp_delta": _stats([float(delta) for delta in qmi_intervals]),
        },
        "static_orientation": {
            "warmup_discard": warmup_discard,
            "mean_axes_mg": mean_axes_mg,
            "dominant_axis": dominant_axis,
            "accel_magnitude_mg": _stats(accel_magnitudes),
            "gyro_abs_mdps": _stats(gyro_abs_values),
        },
        "source_boundary": {
            "source_availability_values": sorted(str(value) for value in source_availability_values),
            "source_status_values": sorted(str(value) for value in source_status_values),
        },
        "gates": gates,
        "quality_gates_passed": not gate_failures,
        "formal_imu_acceptance": False,
        "formal_imu_acceptance_reasons": formal_reasons or ["requires_longer_manual_acceptance"],
    }


def format_markdown(report: dict[str, Any], source_path: Path | None = None) -> str:
    gate_rows = []
    for name, gate in report["gates"].items():
        gate_rows.append(f"| `{name}` | {'PASS' if gate['passed'] else 'FAIL'} | {gate['reason']} |")

    timing = report["timing"]
    orientation = report["static_orientation"]
    identity = report["identity"]

    lines = [
        "# TIMU-002 QMI8658 Sample Quality Report",
        "",
        f"- Source: `{source_path}`" if source_path else "- Source: not recorded",
        f"- QMI8658 WHOAMI: `{identity.get('whoami')}` expected `{identity.get('whoami_expected')}`",
        f"- Sample count: `{report['message_counts']['imu_sample']}`",
        f"- Expected interval: `{timing.get('expected_interval_ms')}` ms",
        f"- Observed mean interval: `{timing['device_interval_ms'].get('mean')}` ms",
        f"- Observed sample Hz: `{timing.get('observed_sample_hz')}`",
        f"- Dominant accel axis: `{orientation['dominant_axis']['axis']}` `{orientation['dominant_axis']['sign']}`",
        f"- Mean accel magnitude: `{orientation['accel_magnitude_mg'].get('mean')}` mg",
        f"- Formal IMU acceptance: `{report['formal_imu_acceptance']}`",
        f"- Formal acceptance reasons: `{', '.join(report['formal_imu_acceptance_reasons'])}`",
        "",
        "## Gates",
        "",
        "| Gate | Result | Meaning |",
        "|---|---:|---|",
        *gate_rows,
        "",
        "## Boundary",
        "",
        "This report is a measurement gate, not a product IMU acceptance. The source",
        "must remain `bridge_uplink/unverified` until ODR, jitter/drop, mounting",
        "direction, orientation, calibration, FIFO/interrupt behavior, and a longer",
        "M1 recording quality gate pass together.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze an AMOLED QMI8658 JSONL capture.")
    parser.add_argument("jsonl_path", type=Path)
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--markdown", type=Path, default=None, help="Write a Markdown report.")
    parser.add_argument("--warmup-discard", type=int, default=5)
    parser.add_argument("--fail-on-unusable", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    messages = load_jsonl(args.jsonl_path)
    report = analyze_imu_messages(messages, warmup_discard=args.warmup_discard)

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(format_markdown(report, args.jsonl_path), encoding="utf-8")

    if args.json or not args.markdown:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.fail_on_unusable and not report["quality_gates_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
