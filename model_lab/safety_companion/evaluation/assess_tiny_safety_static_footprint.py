"""Assess static footprint for the Tiny Safety v0 artifact.

This tool reads existing MODEL-DEVICE-001 export files and, optionally, an
already-built firmware app binary. It never trains a model, contacts hardware,
or infers runtime RAM, latency, or power from static files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = (
    REPO_ROOT
    / "model_artifacts"
    / "tiny_safety_model"
    / "MODEL-DEVICE-001-tiny-safety-v0-20260707"
)
DEFAULT_ARTIFACT = DEFAULT_MODEL_DIR / "tiny_safety_model.json"
DEFAULT_EXPORT_DIR = DEFAULT_MODEL_DIR / "export"
DEFAULT_HEADER = DEFAULT_EXPORT_DIR / "tiny_safety_model.h"
DEFAULT_EXPORT_REPORT = DEFAULT_EXPORT_DIR / "tiny_safety_model_export.json"
DEFAULT_TEST_VECTORS = DEFAULT_EXPORT_DIR / "tiny_safety_test_vectors.json"
DEFAULT_FIRMWARE_BINARY = (
    REPO_ROOT
    / "firmware"
    / "mqtt_heartbeat"
    / "build_model_device_006_tiny_safety"
    / "egolink_mqtt_heartbeat.bin"
)
DEFAULT_OUTPUT_DIR = DEFAULT_MODEL_DIR / "assessment"
REPORT_JSON = "tiny_safety_static_footprint.json"
REPORT_MARKDOWN = "tiny_safety_static_footprint.md"
SHA256 = "sha256.txt"
UNKNOWN = "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON must be an object: {path}")
    return payload


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def relative_path(path: Path | None) -> str:
    if path is None:
        return UNKNOWN
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise FileNotFoundError(path)
        return {
            "path": relative_path(path),
            "present": False,
            "bytes": UNKNOWN,
            "sha256": UNKNOWN,
        }
    return {
        "path": relative_path(path),
        "present": True,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def utf8_c_string_bytes(values: list[str]) -> int:
    return sum(len(value.encode("utf-8")) + 1 for value in values)


def linear_model_static_metrics(artifact: Mapping[str, Any]) -> dict[str, Any]:
    linear = as_dict(artifact.get("linear_model"))
    feature_names = [str(item) for item in as_list(linear.get("feature_names"))]
    state_labels = [str(item) for item in as_list(linear.get("state_labels"))]
    weights = as_list(linear.get("weights"))
    biases = as_list(linear.get("biases"))
    test_vectors = as_list(artifact.get("test_vectors"))

    feature_count = len(feature_names)
    class_count = len(state_labels)
    weight_count = sum(len(as_list(row)) for row in weights)
    bias_count = len(biases)
    vector_count = len(test_vectors)
    test_feature_count = sum(len(as_list(as_dict(vector).get("features"))) for vector in test_vectors)

    float32_model_bytes = (weight_count + bias_count) * 4
    test_feature_bytes = test_feature_count * 4
    test_expected_bytes = vector_count
    feature_name_bytes = utf8_c_string_bytes(feature_names)
    state_label_bytes = utf8_c_string_bytes(state_labels)
    estimated_constant_bytes = (
        float32_model_bytes
        + test_feature_bytes
        + test_expected_bytes
        + feature_name_bytes
        + state_label_bytes
    )

    return {
        "feature_count": feature_count,
        "class_count": class_count,
        "test_vector_count": vector_count,
        "parameter_count": weight_count + bias_count,
        "weight_count": weight_count,
        "bias_count": bias_count,
        "float32_model_bytes": float32_model_bytes,
        "test_feature_bytes": test_feature_bytes,
        "test_expected_bytes": test_expected_bytes,
        "feature_name_bytes": feature_name_bytes,
        "state_label_bytes": state_label_bytes,
        "estimated_c_constant_bytes": estimated_constant_bytes,
    }


def operation_estimate(static_metrics: Mapping[str, Any]) -> dict[str, Any]:
    feature_count = int(static_metrics["feature_count"])
    class_count = int(static_metrics["class_count"])
    score_terms = feature_count * class_count
    return {
        "estimate_basis": "firmware tiny_safety_harness.c float32 linear score loop",
        "feature_extract_slots": feature_count,
        "score_multiply_count": score_terms,
        "score_add_count": score_terms,
        "argmax_class_comparisons": class_count,
        "confidence_expf_calls": class_count,
        "test_vector_score_multiply_count": score_terms * int(static_metrics["test_vector_count"]),
        "notes": [
            "Counts are static source-level estimates, not measured CPU cycles.",
            "The current firmware computes confidence with expf; latency remains unknown until measured on target.",
        ],
    }


def build_report(
    *,
    artifact_path: Path,
    export_report_path: Path,
    header_path: Path,
    test_vectors_path: Path,
    firmware_binary_path: Path | None,
    firmware_version: str,
    test_run_id: str,
    assessed_at: str,
) -> dict[str, Any]:
    artifact = read_json(artifact_path)
    export_report = read_json(export_report_path)
    static_metrics = linear_model_static_metrics(artifact)
    firmware_record = (
        file_record(firmware_binary_path, required=False)
        if firmware_binary_path is not None
        else {"path": UNKNOWN, "present": False, "bytes": UNKNOWN, "sha256": UNKNOWN}
    )
    evidence_level = (
        "L2_build_verified_static_partial"
        if firmware_record["present"]
        else "L1_artifact_estimated"
    )
    flash_total_bytes: int | str = (
        int(firmware_record["bytes"]) if firmware_record["present"] else UNKNOWN
    )

    return {
        "schema_version": "egolink.tiny_safety_static_footprint.v0.1",
        "assessed_at": assessed_at,
        "serves_demo": "D4-D5",
        "model_id": artifact.get("model_id"),
        "model_version": artifact.get("model_version"),
        "model_name": artifact.get("model_name"),
        "model_type": artifact.get("model_type"),
        "artifact_hash": file_sha256(artifact_path),
        "input_manifest": as_dict(artifact.get("paths")).get("synthetic_eval_jsonl", UNKNOWN),
        "runtime_backend": "esp32_s3_c_float32_tiny_safety_harness",
        "firmware_or_benchmark_version": firmware_version or UNKNOWN,
        "firmware_test_run_id": test_run_id or UNKNOWN,
        "hardware_candidate": "esp32_s3_connectivity_node" if firmware_record["present"] else UNKNOWN,
        "evidence_level": evidence_level,
        "source_status": "static_files_only_no_runtime_measurement",
        "artifact_files": {
            "model_artifact": file_record(artifact_path),
            "export_report": file_record(export_report_path),
            "c_header": file_record(header_path),
            "test_vectors": file_record(test_vectors_path),
            "firmware_binary": firmware_record,
        },
        "export_scope": {
            "firmware_integrated": as_dict(export_report.get("deployment")).get("firmware_integrated"),
            "device_deployed": as_dict(export_report.get("deployment")).get("device_deployed"),
            "hardware_contacted": as_dict(export_report.get("scope")).get("hardware_contacted"),
            "synthetic_only": as_dict(export_report.get("scope")).get("synthetic_only"),
        },
        "static_model_metrics": static_metrics,
        "operation_estimate": operation_estimate(static_metrics),
        "model_footprint_manifest": {
            "ram_peak_bytes": UNKNOWN,
            "flash_total_bytes": flash_total_bytes,
            "model_static_delta_bytes": UNKNOWN,
            "latency_p50_ms": UNKNOWN,
            "latency_p95_ms": UNKNOWN,
            "latency_max_ms": UNKNOWN,
            "energy_per_inference_mj": UNKNOWN,
            "power_profile": UNKNOWN,
            "measurement_environment": "windows_static_file_assessment",
            "reviewer_outcome": "engineering_static_evidence_only",
            "evidence_paths": [
                relative_path(artifact_path),
                relative_path(export_report_path),
                relative_path(header_path),
                relative_path(test_vectors_path),
                relative_path(firmware_binary_path) if firmware_record["present"] else UNKNOWN,
            ],
        },
        "known_gaps": [
            "Runtime RAM is unknown until measured on a target build.",
            "Latency is unknown until measured on a target build.",
            "Energy per inference is unknown until measured with a power path.",
            "Firmware app bytes are not the model static delta.",
            "Tiny Safety v0 is not MotionNet-class acceptance evidence.",
            "PROD-001 TBD(MODEL-001) values must not be replaced from this report.",
        ],
        "scope": {
            "hardware_contacted": False,
            "firmware_changed": False,
            "model_training_started": False,
            "model_behavior_changed": False,
            "contracts_changed": False,
            "runtime_measured": False,
            "power_measured": False,
            "prod_001_update_allowed": False,
        },
        "non_claims": [
            "No real-world accuracy is claimed.",
            "No runtime RAM, latency, or power measurement is claimed.",
            "No MotionNet acceptance or production MCU selection is claimed.",
            "No real SMS, call, dispatch, or external escalation is enabled.",
        ],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    metrics = as_dict(report.get("static_model_metrics"))
    manifest = as_dict(report.get("model_footprint_manifest"))
    files = as_dict(report.get("artifact_files"))
    firmware = as_dict(files.get("firmware_binary"))
    lines = [
        "# Tiny Safety Static Footprint",
        "",
        f"- Model ID: `{report['model_id']}`",
        f"- Model version: `{report['model_version']}`",
        f"- Evidence level: `{report['evidence_level']}`",
        f"- Artifact hash: `{report['artifact_hash']}`",
        f"- Features/classes: `{metrics['feature_count']} / {metrics['class_count']}`",
        f"- Parameters: `{metrics['parameter_count']}`",
        f"- Estimated C constants: `{metrics['estimated_c_constant_bytes']}` bytes",
        f"- Firmware app bytes: `{manifest['flash_total_bytes']}`",
        f"- Firmware binary present: `{firmware.get('present')}`",
        "",
        "## Static Operation Estimate",
        "",
        f"- Score multiplies: `{report['operation_estimate']['score_multiply_count']}`",
        f"- Score adds: `{report['operation_estimate']['score_add_count']}`",
        f"- Confidence expf calls: `{report['operation_estimate']['confidence_expf_calls']}`",
        "",
        "## Unknown Until Measured",
        "",
        f"- RAM peak bytes: `{manifest['ram_peak_bytes']}`",
        f"- Latency P50/P95/max: `{manifest['latency_p50_ms']} / {manifest['latency_p95_ms']} / {manifest['latency_max_ms']}`",
        f"- Energy per inference: `{manifest['energy_per_inference_mj']}`",
        "",
        "## Known Gaps",
        "",
    ]
    lines.extend(f"- {item}" for item in report["known_gaps"])
    lines += ["", "## Non-Claims", ""]
    lines.extend(f"- {item}" for item in report["non_claims"])
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_sha256(path: Path, files: list[Path]) -> None:
    lines = [f"{file_sha256(file_path)}  {file_path.name}" for file_path in files]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / REPORT_JSON
    markdown_path = output_dir / REPORT_MARKDOWN
    sha_path = output_dir / SHA256
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    write_sha256(sha_path, [json_path, markdown_path])
    return {
        "report_json": relative_path(json_path),
        "report_markdown": relative_path(markdown_path),
        "sha256": relative_path(sha_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--export-report", type=Path, default=DEFAULT_EXPORT_REPORT)
    parser.add_argument("--header", type=Path, default=DEFAULT_HEADER)
    parser.add_argument("--test-vectors", type=Path, default=DEFAULT_TEST_VECTORS)
    parser.add_argument("--firmware-binary", type=Path, default=DEFAULT_FIRMWARE_BINARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--firmware-version", default="")
    parser.add_argument("--test-run-id", default="")
    parser.add_argument("--assessed-at", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        artifact_path=args.model_artifact,
        export_report_path=args.export_report,
        header_path=args.header,
        test_vectors_path=args.test_vectors,
        firmware_binary_path=args.firmware_binary,
        firmware_version=args.firmware_version,
        test_run_id=args.test_run_id,
        assessed_at=args.assessed_at or utc_now(),
    )
    paths = write_report(report, args.output_dir)
    output = {**report, "paths": paths}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PASS tiny safety static footprint: {paths['report_markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
