"""Build a training-blocked labelled IMU seed from explicit local artifacts.

Labels are accepted only from a post-capture, operator-confirmed annotation
sidecar bound one-to-one by ``cmd_id``, ``window_id``, and ``samples_sha256``.
The exporter JSONL is read-only and is never modified by this tool.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_imu_capture_session as capture


ANNOTATIONS_SCHEMA_VERSION = "egolink.imu_window_annotations.v0.1"
LABELLED_ROW_SCHEMA_VERSION = "egolink.labelled_imu_window.v0.1"
DATASET_MANIFEST_SCHEMA_VERSION = "egolink.labelled_imu_dataset_manifest.v0.1"
CONFIRMED_LABELS = frozenset({"stationary", "walking", "transition_or_unknown"})
TARGET_LABELS = frozenset({"stationary", "walking"})
LABEL_CONFIDENCE_VALUES = frozenset({"low", "medium", "high"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRAINING_BLOCKERS = [
    "operator_training_authorization_missing",
    "consent_unreviewed",
    "mounting_axis_calibration_unrecorded",
    "dataset_size_insufficient",
    "training_promotion_not_part_of_seed_builder",
]


class DatasetBuildError(RuntimeError):
    """Input lineage, quality, annotation, or privacy checks failed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DatasetBuildError(f"{name} must be a JSON object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise DatasetBuildError(
            f"{name} fields mismatch: missing={sorted(expected - set(value))}, unexpected={sorted(set(value) - expected)}"
        )


def _read_json(path: Path, name: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DatasetBuildError(f"cannot read {name} {path.name}: {error}") from error
    return _object(value, name), raw


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DatasetBuildError(f"cannot read IMU export {path.name}: {error}") from error
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(_object(json.loads(line), f"imu_windows line {line_number}"))
        except json.JSONDecodeError as error:
            raise DatasetBuildError(f"invalid JSON on IMU export line {line_number}: {error}") from error
    if not rows:
        raise DatasetBuildError("IMU export contains no windows")
    return rows, raw


def _validate_execution(
    execution: dict[str, Any], plan: dict[str, Any], plan_sha256: str
) -> dict[str, dict[str, Any]]:
    if execution.get("schema_version") != capture.EXECUTION_SCHEMA_VERSION:
        raise DatasetBuildError("execution schema_version mismatch")
    if (
        execution.get("plan_id") != plan["plan_id"]
        or execution.get("plan_sha256") != plan_sha256
        or execution.get("device_id") != plan["device_id"]
        or execution.get("test_run_id") != plan["test_run_id"]
        or execution.get("mode") != "execute"
        or execution.get("status") != "completed"
        or execution.get("planned_window_count") != capture.MAX_WINDOWS
        or execution.get("completed_window_count") != capture.MAX_WINDOWS
        or execution.get("test_run_created") is not True
        or execution.get("training_allowed") is not False
    ):
        raise DatasetBuildError("execution is not a completed, training-blocked run of the exact plan")
    planned = {window["cmd_id"]: (session, window) for session, window in capture.iter_planned_windows(plan)}
    if execution.get("commands_created") != list(planned):
        raise DatasetBuildError("execution commands_created does not exactly match plan order")
    actions = execution.get("external_actions")
    if not isinstance(actions, list) or len(actions) != len(planned) + 1:
        raise DatasetBuildError("execution external_actions is incomplete")
    if actions[0] != {"action": "create_test_run", "test_run_id": plan["test_run_id"], "state": "ok"}:
        raise DatasetBuildError("execution test-run action is invalid")
    for action, cmd_id in zip(actions[1:], planned):
        if action != {"action": "create_command", "cmd_id": cmd_id, "state": "ok"}:
            raise DatasetBuildError(f"execution command action is invalid for {cmd_id}")
    results = execution.get("results")
    if not isinstance(results, list) or len(results) != len(planned):
        raise DatasetBuildError("execution result count does not match the plan")
    indexed: dict[str, dict[str, Any]] = {}
    window_ids: set[str] = set()
    for index, raw_result in enumerate(results):
        result = _object(raw_result, f"execution.results[{index}]")
        cmd_id = result.get("cmd_id")
        if cmd_id not in planned or cmd_id in indexed:
            raise DatasetBuildError(f"execution has an unknown or duplicate cmd_id: {cmd_id}")
        session, window = planned[str(cmd_id)]
        if (
            result.get("session_id") != session["session_id"]
            or result.get("split_name") != session["split_name"]
            or result.get("planned_activity") != window["planned_activity"]
            or result.get("state") != "ok"
            or result.get("training_allowed") is not False
        ):
            raise DatasetBuildError(f"execution result lineage/status mismatch for {cmd_id}")
        ack = result.get("ack")
        evidence = result.get("window")
        if not isinstance(ack, dict) or (
            ack.get("status") != "ok"
            or ack.get("test_run_id") != plan["test_run_id"]
            or ack.get("transport_type") != "wifi"
            or ack.get("duplicate_local_execution_prevented") is not False
        ):
            raise DatasetBuildError(f"execution ACK evidence is invalid for {cmd_id}")
        if not isinstance(evidence, dict) or (
            evidence.get("source") != "qmi8658_i2c"
            or evidence.get("source_status") != "observed"
            or evidence.get("transport_type") != "wifi"
            or evidence.get("cadence_quality_status") != "qualified"
            or evidence.get("training_allowed") is not False
        ):
            raise DatasetBuildError(f"execution window evidence is invalid for {cmd_id}")
        window_id = evidence.get("window_id")
        if not isinstance(window_id, str) or not window_id or window_id in window_ids:
            raise DatasetBuildError("execution contains a missing or duplicate window_id")
        window_ids.add(window_id)
        indexed[str(cmd_id)] = result
    return indexed


def _validate_annotations(
    sidecar: dict[str, Any],
    *,
    plan: dict[str, Any],
    plan_sha256: str,
    execution_sha256: str,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    _exact_keys(
        sidecar,
        {"schema_version", "plan_id", "plan_sha256", "execution_sha256", "annotations"},
        "annotations sidecar",
    )
    if (
        sidecar["schema_version"] != ANNOTATIONS_SCHEMA_VERSION
        or sidecar["plan_id"] != plan["plan_id"]
        or sidecar["plan_sha256"] != plan_sha256
        or sidecar["execution_sha256"] != execution_sha256
    ):
        raise DatasetBuildError("annotations sidecar does not bind to the exact plan and execution")
    annotations = sidecar["annotations"]
    if not isinstance(annotations, list):
        raise DatasetBuildError("annotations must be an array")
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    annotation_ids: set[str] = set()
    planned_by_cmd = {window["cmd_id"]: session for session, window in capture.iter_planned_windows(plan)}
    for index, raw_annotation in enumerate(annotations):
        annotation = _object(raw_annotation, f"annotations[{index}]")
        _exact_keys(
            annotation,
            {
                "annotation_id",
                "session_id",
                "cmd_id",
                "window_id",
                "samples_sha256",
                "activity_label",
                "label_source",
                "label_confidence",
                "review_state",
                "created_at",
            },
            f"annotations[{index}]",
        )
        digest = annotation["samples_sha256"]
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise DatasetBuildError(f"annotations[{index}].samples_sha256 is invalid")
        if annotation["activity_label"] not in CONFIRMED_LABELS:
            raise DatasetBuildError(f"annotations[{index}].activity_label is not permitted in this safe seed")
        annotation_id = annotation["annotation_id"]
        if (
            not isinstance(annotation_id, str)
            or not annotation_id
            or len(annotation_id) > 64
            or capture.ID_RE.fullmatch(annotation_id) is None
            or annotation_id in annotation_ids
        ):
            raise DatasetBuildError(f"annotations[{index}].annotation_id is invalid or duplicated")
        annotation_ids.add(annotation_id)
        session = planned_by_cmd.get(annotation["cmd_id"])
        if session is None or annotation["session_id"] != session["session_id"]:
            raise DatasetBuildError(f"annotations[{index}] cmd_id/session_id does not match the plan")
        if annotation["label_source"] != "operator_direct_observation":
            raise DatasetBuildError(f"annotations[{index}].label_source must be operator_direct_observation")
        if annotation["label_confidence"] not in LABEL_CONFIDENCE_VALUES:
            raise DatasetBuildError(f"annotations[{index}].label_confidence is invalid")
        if annotation["review_state"] != "operator_confirmed":
            raise DatasetBuildError(f"annotations[{index}] is not operator_confirmed")
        created_at = annotation["created_at"]
        if not isinstance(created_at, str):
            raise DatasetBuildError(f"annotations[{index}].created_at must be an ISO-8601 timestamp")
        try:
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise DatasetBuildError(f"annotations[{index}].created_at is invalid") from error
        if timestamp.tzinfo is None:
            raise DatasetBuildError(f"annotations[{index}].created_at must include a timezone")
        key = (str(annotation["cmd_id"]), str(annotation["window_id"]), digest)
        if key in indexed:
            raise DatasetBuildError(f"duplicate annotation binding for {key[0]}")
        indexed[key] = annotation
    return indexed


def _validate_export_manifest(
    manifest: dict[str, Any], *, imu_windows_path: Path, source_sha256: str, plan: dict[str, Any]
) -> None:
    selectors = manifest.get("selectors")
    summary = manifest.get("summary")
    privacy = manifest.get("privacy")
    outputs = manifest.get("outputs")
    if manifest.get("schema_version") != "egolink.imu_window_export.v1" or manifest.get("ok") is not True:
        raise DatasetBuildError("exporter manifest is not an ok egolink.imu_window_export.v1 artifact")
    if not isinstance(selectors, dict) or (
        selectors.get("device_id") != plan["device_id"] or selectors.get("test_run_id") != plan["test_run_id"]
    ):
        raise DatasetBuildError("exporter manifest selectors do not match the plan")
    if not isinstance(summary, dict) or (
        summary.get("truncated") is not False
        or summary.get("valid_windows") != capture.MAX_WINDOWS
        or summary.get("invalid_windows") != 0
        or summary.get("cadence_qualified_windows") != capture.MAX_WINDOWS
    ):
        raise DatasetBuildError("exporter manifest is truncated, incomplete, invalid, or cadence-unqualified")
    if manifest.get("invalid") != []:
        raise DatasetBuildError("exporter manifest contains invalid windows")
    if not isinstance(privacy, dict) or privacy.get("training_allowed") is not False:
        raise DatasetBuildError("exporter manifest does not preserve the training gate")
    if not isinstance(outputs, dict) or (
        outputs.get("imu_windows_jsonl") != imu_windows_path.name
        or outputs.get("imu_windows_jsonl_sha256") != source_sha256
    ):
        raise DatasetBuildError("exporter manifest does not bind to the explicit IMU JSONL")


def _guard_output_paths(output_dir: Path, inputs: list[Path]) -> tuple[Path, Path]:
    labelled_path = (output_dir / "labelled_imu_windows.jsonl").resolve()
    manifest_path = (output_dir / "labelled_imu_dataset_manifest.json").resolve()
    resolved_inputs = {path.resolve() for path in inputs}
    if output_dir.resolve() in resolved_inputs or labelled_path in resolved_inputs or manifest_path in resolved_inputs:
        raise DatasetBuildError("output paths must not overwrite any input artifact")
    return labelled_path, manifest_path


def _sample_bytes(samples: Any, *, cmd_id: str) -> bytes:
    if not isinstance(samples, list) or len(samples) != capture.SAMPLE_COUNT:
        raise DatasetBuildError(f"source {cmd_id} must contain exactly 100 samples")
    payload = bytearray()
    previous_offset = -1
    for index, sample_value in enumerate(samples):
        sample = _object(sample_value, f"source {cmd_id} sample {index}")
        if sample.get("index") != index:
            raise DatasetBuildError(f"source {cmd_id} sample indices are not contiguous")
        offset = sample.get("offset_us")
        accel = sample.get("accel_mg")
        gyro = sample.get("gyro_mdps")
        if type(offset) is not int or offset <= previous_offset:
            raise DatasetBuildError(f"source {cmd_id} sample offsets are not strictly increasing")
        if (
            not isinstance(accel, list)
            or not isinstance(gyro, list)
            or len(accel) != 3
            or len(gyro) != 3
            or any(type(value) is not int for value in accel + gyro)
        ):
            raise DatasetBuildError(f"source {cmd_id} sample axes are invalid")
        try:
            payload.extend(struct.pack("<Iiiiiii", offset, *(accel + gyro)))
        except struct.error as error:
            raise DatasetBuildError(f"source {cmd_id} sample is outside the v1 integer range") from error
        previous_offset = offset
    return bytes(payload)


def _validate_source_row(row: dict[str, Any], *, plan: dict[str, Any]) -> tuple[str, str, str]:
    cmd_id = row.get("capture_cmd_id")
    window_id = row.get("window_id")
    digest = row.get("samples_sha256")
    if not isinstance(cmd_id, str) or not isinstance(window_id, str) or not isinstance(digest, str):
        raise DatasetBuildError("source row is missing cmd/window/samples hash lineage")
    if SHA256_RE.fullmatch(digest) is None:
        raise DatasetBuildError(f"source {cmd_id} samples_sha256 is invalid")
    if (
        row.get("contract_version") != "egolink.imu_window.v1"
        or row.get("device_id") != plan["device_id"]
        or row.get("test_run_id") != plan["test_run_id"]
        or row.get("source") != "qmi8658_i2c"
        or row.get("source_status") != "observed"
        or row.get("transport_type") != "wifi"
        or row.get("activity_label") != "unknown"
        or row.get("label_source") != "none"
        or row.get("training_allowed") is not False
    ):
        raise DatasetBuildError(f"source {cmd_id} violates device evidence/privacy lineage")
    capture_data = row.get("capture")
    if not isinstance(capture_data, dict) or (
        capture_data.get("sample_count") != capture.SAMPLE_COUNT
        or capture_data.get("requested_interval_us") != capture.INTERVAL_MS * 1000
        or capture_data.get("read_failure_count") != 0
        or capture_data.get("mock_sample_count") != 0
        or capture_data.get("cadence_quality_status") != "qualified"
        or type(capture_data.get("min_interval_us")) is not int
        or capture_data["min_interval_us"] < 40_000
        or type(capture_data.get("mean_interval_us")) is not int
        or not 45_000 <= capture_data["mean_interval_us"] <= 55_000
        or type(capture_data.get("max_interval_us")) is not int
        or capture_data["max_interval_us"] > 60_000
        or type(capture_data.get("deadline_miss_count")) is not int
        or capture_data["deadline_miss_count"] > 5
    ):
        raise DatasetBuildError(f"source {cmd_id} failed fixed capture/cadence quality checks")
    actual_digest = _sha256(_sample_bytes(row.get("samples"), cmd_id=cmd_id))
    if actual_digest != digest:
        raise DatasetBuildError(f"source {cmd_id} samples_sha256 does not match sample content")
    return cmd_id, window_id, digest


def build_dataset(
    *,
    imu_windows_path: Path,
    export_manifest_path: Path,
    plan_path: Path,
    execution_path: Path,
    annotations_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    labelled_path, manifest_path = _guard_output_paths(
        output_dir, [imu_windows_path, export_manifest_path, plan_path, execution_path, annotations_path]
    )
    plan_value, plan_raw = _read_json(plan_path, "plan")
    try:
        plan = capture.validate_plan(plan_value)
    except capture.CaptureSessionError as error:
        raise DatasetBuildError(str(error)) from error
    plan_sha256 = _sha256(plan_raw)
    execution, execution_raw = _read_json(execution_path, "execution")
    execution_sha256 = _sha256(execution_raw)
    execution_by_cmd = _validate_execution(execution, plan, plan_sha256)
    sidecar, annotations_raw = _read_json(annotations_path, "annotations")
    annotations = _validate_annotations(
        sidecar,
        plan=plan,
        plan_sha256=plan_sha256,
        execution_sha256=execution_sha256,
    )
    source_rows, source_raw = _read_jsonl(imu_windows_path)
    source_sha256 = _sha256(source_raw)
    export_manifest, _ = _read_json(export_manifest_path, "exporter manifest")
    _validate_export_manifest(export_manifest, imu_windows_path=imu_windows_path, source_sha256=source_sha256, plan=plan)

    planned_by_cmd = {window["cmd_id"]: (session, window) for session, window in capture.iter_planned_windows(plan)}
    source_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    seen_windows: set[str] = set()
    seen_hashes: set[str] = set()
    for row in source_rows:
        key = _validate_source_row(row, plan=plan)
        cmd_id, window_id, digest = key
        if cmd_id not in planned_by_cmd or cmd_id in {existing[0] for existing in source_by_key}:
            raise DatasetBuildError(f"source has an unknown or duplicate cmd_id: {cmd_id}")
        if window_id in seen_windows or digest in seen_hashes:
            raise DatasetBuildError("duplicate window_id or samples_sha256 is forbidden across sessions/splits")
        result = execution_by_cmd[cmd_id]
        if result["window"].get("window_id") != window_id:
            raise DatasetBuildError(f"execution/source window_id mismatch for {cmd_id}")
        seen_windows.add(window_id)
        seen_hashes.add(digest)
        source_by_key[key] = row
    if len(source_by_key) != len(planned_by_cmd):
        raise DatasetBuildError("source windows are not an exact one-to-one match for the capture plan")
    if set(annotations) != set(source_by_key):
        missing = set(source_by_key) - set(annotations)
        extra = set(annotations) - set(source_by_key)
        raise DatasetBuildError(f"annotation bindings are not an exact one-to-one match: missing={len(missing)}, extra={len(extra)}")

    labelled_rows: list[dict[str, Any]] = []
    split_counts = {name: 0 for name in sorted(capture.SPLIT_NAMES)}
    label_counts = {name: 0 for name in sorted(CONFIRMED_LABELS)}
    for key, source in source_by_key.items():
        cmd_id, window_id, digest = key
        session, planned_window = planned_by_cmd[cmd_id]
        annotation = annotations[key]
        label = annotation["activity_label"]
        role = "target" if label in TARGET_LABELS else "exclusion"
        row = {
            "schema_version": LABELLED_ROW_SCHEMA_VERSION,
            "record_id": "imuls-" + _sha256("|".join(key).encode("utf-8"))[:20],
            "plan_id": plan["plan_id"],
            "session_id": session["session_id"],
            "split_name": session["split_name"],
            "split_group_key": session["session_id"],
            "cmd_id": cmd_id,
            "window_id": window_id,
            "samples_sha256": digest,
            "planned_activity": planned_window["planned_activity"],
            "activity_label": label,
            "label_source": "operator_confirmed_annotation_sidecar",
            "annotation_id": annotation["annotation_id"],
            "annotation_created_at": annotation["created_at"],
            "label_confidence": annotation["label_confidence"],
            "review_state": "operator_confirmed",
            "dataset_role": role,
            "source_contract_version": source["contract_version"],
            "device_id": source["device_id"],
            "fw_version": source.get("fw_version"),
            "test_run_id": source["test_run_id"],
            "transport_type": source["transport_type"],
            "source": source["source"],
            "source_status": source["source_status"],
            "sensor": source.get("sensor"),
            "capture": source["capture"],
            "samples": source["samples"],
            "training_allowed": False,
            "training_ready": False,
            "training_blockers": list(TRAINING_BLOCKERS),
        }
        labelled_rows.append(row)
        split_counts[session["split_name"]] += 1
        label_counts[label] += 1
    labelled_rows.sort(key=lambda row: [row["session_id"], row["cmd_id"]])
    if not any(row["dataset_role"] == "target" for row in labelled_rows):
        raise DatasetBuildError("all confirmed annotations are exclusions; no stationary/walking seed remains")
    if _sha256(imu_windows_path.read_bytes()) != source_sha256:
        raise DatasetBuildError("source IMU export changed while the dataset was being built")

    jsonl_bytes = b"".join((_stable_json(row) + "\n").encode("utf-8") for row in labelled_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    labelled_path.write_bytes(jsonl_bytes)
    manifest: dict[str, Any] = {
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "status": "pipeline_seed_ready",
        "pipeline_seed_ready": True,
        "training_ready": False,
        "training_allowed": False,
        "plan_id": plan["plan_id"],
        "device_id": plan["device_id"],
        "test_run_id": plan["test_run_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_immutable": True,
        "lineage": {
            "plan_sha256": plan_sha256,
            "execution_sha256": execution_sha256,
            "annotations_sha256": _sha256(annotations_raw),
            "imu_windows_jsonl_sha256": source_sha256,
        },
        "summary": {
            "window_count": len(labelled_rows),
            "session_count": len(plan["sessions"]),
            "target_window_count": sum(row["dataset_role"] == "target" for row in labelled_rows),
            "exclusion_window_count": sum(row["dataset_role"] == "exclusion" for row in labelled_rows),
            "split_counts": split_counts,
            "label_counts": label_counts,
        },
        "privacy": {
            "labels_and_consent_separate": True,
            "consent_status": "not_collected_by_this_tool",
            "training_allowed": False,
            "training_ready": False,
            "training_blockers": list(TRAINING_BLOCKERS),
        },
        "outputs": {
            "labelled_imu_windows": labelled_path.name,
            "labelled_imu_windows_sha256": _sha256(jsonl_bytes),
            "manifest": manifest_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imu-windows", required=True, type=Path)
    parser.add_argument("--export-manifest", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_dataset(
            imu_windows_path=args.imu_windows,
            export_manifest_path=args.export_manifest,
            plan_path=args.plan,
            execution_path=args.execution,
            annotations_path=args.annotations,
            output_dir=args.output_dir,
        )
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
