from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ARTIFACT_SCHEMA_VERSION = "egolink.imu_calibration_artifact.v0.1"
CALIBRATED_WINDOW_SCHEMA_VERSION = "egolink.imu_calibrated_window.v0.1"
METADATA_SCHEMA_VERSION = "egolink.imu_calibration_metadata.v0.1"
SOURCE_CONTRACT_VERSION = "egolink.imu_window.v1"
ESTIMATOR_VERSION = "egolink.imu_six_face_calibration.v0.1"

SAMPLE_COUNT = 100
REQUESTED_INTERVAL_US = 50_000
CURRENT_CAPTURE_RATE_HZ = 20.0
SAMPLE_RECORD_BYTES = 28
G_STANDARD_M_S2 = 9.80665
MG_TO_M_S2 = G_STANDARD_M_S2 / 1000.0
MDPS_TO_RAD_S = math.pi / 180_000.0

FACE_ROLES = (
    "x_positive",
    "x_negative",
    "y_positive",
    "y_negative",
    "z_positive",
    "z_negative",
)
GYRO_ROLE = "gyro_stationary"
SOURCE_ROLES = FACE_ROLES + (GYRO_ROLE,)
AXES = ("x", "y", "z")
FACE_EXPECTATIONS = {
    "x_positive": (0, 1),
    "x_negative": (0, -1),
    "y_positive": (1, 1),
    "y_negative": (1, -1),
    "z_positive": (2, 1),
    "z_negative": (2, -1),
}

MIN_ACCEL_NORM_MG = 800.0
MAX_ACCEL_NORM_MG = 1200.0
MAX_ACCEL_NORM_STDDEV_MG = 50.0
MIN_FACE_DOMINANT_MG = 700.0
MAX_FACE_OFF_AXIS_MEAN_MG = 300.0
MAX_STATIC_GYRO_MEAN_MDPS = 20_000.0
MAX_STATIC_GYRO_STDDEV_MDPS = 5_000.0
MIN_SENSITIVITY_MG_PER_G = 700.0
MAX_SENSITIVITY_MG_PER_G = 1300.0
MAX_ACCEL_BIAS_MG = 300.0
MAX_PRIMARY_RESIDUAL_MG = 100.0
MAX_OFF_AXIS_RESIDUAL_MG = 150.0

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "imu_calibration_artifact.schema.json"
CALIBRATED_WINDOW_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "imu_calibrated_window.schema.json"

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ImuCalibrationError(ValueError):
    """Raised when calibration input cannot produce an honest artifact."""


def stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ImuCalibrationError(f"{name} must be a JSON object")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], name: str) -> None:
    actual = set(value)
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        raise ImuCalibrationError(f"{name} keys mismatch; missing={missing}, extra={extra}")


def _text(value: Any, name: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImuCalibrationError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if pattern is not None and pattern.fullmatch(normalized) is None:
        raise ImuCalibrationError(f"{name} has an invalid format")
    return normalized


def _utc_timestamp(value: Any, name: str) -> str:
    raw = _text(value, name)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ImuCalibrationError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ImuCalibrationError(f"{name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_metadata(value: dict[str, Any]) -> dict[str, Any]:
    metadata = _mapping(value, "metadata")
    _exact_keys(
        metadata,
        {
            "schema_version",
            "calibration_run_id",
            "calibration_time_utc",
            "calibration_time_source",
            "device_id",
            "board_id",
            "hardware_revision",
            "hardware_profile",
            "mounting_profile_id",
            "body_axis_mapping_status",
            "imu_model",
            "imu_module",
            "sensor_i2c_address",
            "test_run_id",
            "firmware",
            "calibration_software_commit",
            "temperature_status",
            "source_windows",
        },
        "metadata",
    )
    if metadata["schema_version"] != METADATA_SCHEMA_VERSION:
        raise ImuCalibrationError(f"metadata.schema_version must be {METADATA_SCHEMA_VERSION}")

    calibration_time_source = _text(
        metadata["calibration_time_source"], "metadata.calibration_time_source"
    )
    if calibration_time_source not in {"operator_provided_utc", "host_clock_utc"}:
        raise ImuCalibrationError(
            "metadata.calibration_time_source must be operator_provided_utc or host_clock_utc"
        )

    firmware = _mapping(metadata["firmware"], "metadata.firmware")
    _exact_keys(
        firmware,
        {"fw_version", "firmware_commit", "firmware_image_sha256"},
        "metadata.firmware",
    )
    source_windows = _mapping(metadata["source_windows"], "metadata.source_windows")
    _exact_keys(source_windows, set(SOURCE_ROLES), "metadata.source_windows")
    normalized_windows = {
        role: _text(source_windows[role], f"metadata.source_windows.{role}", pattern=SAFE_ID_RE)
        for role in SOURCE_ROLES
    }
    if len(set(normalized_windows.values())) != len(SOURCE_ROLES):
        raise ImuCalibrationError("metadata.source_windows must bind seven unique windows")

    i2c_address = metadata["sensor_i2c_address"]
    if type(i2c_address) is not int or not 0 <= i2c_address <= 127:
        raise ImuCalibrationError("metadata.sensor_i2c_address must be an integer from 0 to 127")
    temperature_status = _text(metadata["temperature_status"], "metadata.temperature_status")
    if temperature_status != "unavailable_in_imu_window_v1":
        raise ImuCalibrationError(
            "metadata.temperature_status must be unavailable_in_imu_window_v1 for this source contract"
        )

    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "calibration_run_id": _text(
            metadata["calibration_run_id"], "metadata.calibration_run_id", pattern=SAFE_ID_RE
        ),
        "calibration_time_utc": _utc_timestamp(
            metadata["calibration_time_utc"], "metadata.calibration_time_utc"
        ),
        "calibration_time_source": calibration_time_source,
        "device_id": _text(metadata["device_id"], "metadata.device_id", pattern=SAFE_ID_RE),
        "board_id": _text(metadata["board_id"], "metadata.board_id", pattern=SAFE_ID_RE),
        "hardware_revision": _text(metadata["hardware_revision"], "metadata.hardware_revision"),
        "hardware_profile": _text(metadata["hardware_profile"], "metadata.hardware_profile"),
        "mounting_profile_id": _text(
            metadata["mounting_profile_id"], "metadata.mounting_profile_id", pattern=SAFE_ID_RE
        ),
        "body_axis_mapping_status": _text(
            metadata["body_axis_mapping_status"], "metadata.body_axis_mapping_status"
        ),
        "imu_model": _text(metadata["imu_model"], "metadata.imu_model"),
        "imu_module": _text(metadata["imu_module"], "metadata.imu_module"),
        "sensor_i2c_address": i2c_address,
        "test_run_id": _text(metadata["test_run_id"], "metadata.test_run_id", pattern=SAFE_ID_RE),
        "firmware": {
            "fw_version": _text(firmware["fw_version"], "metadata.firmware.fw_version"),
            "firmware_commit": _text(
                firmware["firmware_commit"], "metadata.firmware.firmware_commit", pattern=GIT_COMMIT_RE
            ).lower(),
            "firmware_image_sha256": _text(
                firmware["firmware_image_sha256"],
                "metadata.firmware.firmware_image_sha256",
                pattern=SHA256_RE,
            ).lower(),
        },
        "calibration_software_commit": _text(
            metadata["calibration_software_commit"],
            "metadata.calibration_software_commit",
            pattern=GIT_COMMIT_RE,
        ).lower(),
        "temperature_status": temperature_status,
        "source_windows": normalized_windows,
    }


def load_export_windows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for raw_path in paths:
        path = raw_path.resolve()
        if path in seen_paths:
            raise ImuCalibrationError(f"duplicate --imu-windows input: {path}")
        seen_paths.add(path)
        if not path.is_file():
            raise ImuCalibrationError(f"IMU window export does not exist: {path}")
        payload = path.read_bytes()
        export_sha256 = sha256_hex(payload)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ImuCalibrationError(f"IMU window export is not UTF-8: {path}") from error
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise ImuCalibrationError(f"invalid JSONL at {path}:{line_number}") from error
            row = dict(_mapping(parsed, f"{path}:{line_number}"))
            row["_source_export_sha256"] = export_sha256
            windows.append(row)
    if not windows:
        raise ImuCalibrationError("no IMU windows were loaded")
    return windows


def _int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ImuCalibrationError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def encode_source_samples(samples: Any, *, window_id: str) -> bytes:
    if not isinstance(samples, list) or len(samples) != SAMPLE_COUNT:
        raise ImuCalibrationError(f"window {window_id} must contain exactly {SAMPLE_COUNT} samples")
    records: list[bytes] = []
    previous_offset: int | None = None
    for index, raw_sample in enumerate(samples):
        sample = _mapping(raw_sample, f"window {window_id} sample {index}")
        if sample.get("index") != index:
            raise ImuCalibrationError(f"window {window_id} sample indices must be contiguous")
        offset_us = _int(sample.get("offset_us"), f"window {window_id} sample {index}.offset_us", minimum=0, maximum=2**32 - 1)
        if previous_offset is not None and offset_us <= previous_offset:
            raise ImuCalibrationError(f"window {window_id} sample offsets must be strictly increasing")
        previous_offset = offset_us
        accel = sample.get("accel_mg")
        gyro = sample.get("gyro_mdps")
        if not isinstance(accel, list) or len(accel) != 3 or not isinstance(gyro, list) or len(gyro) != 3:
            raise ImuCalibrationError(f"window {window_id} sample {index} must contain three accel and gyro axes")
        axes = [
            _int(axis, f"window {window_id} sample {index} axis", minimum=-(2**31), maximum=2**31 - 1)
            for axis in [*accel, *gyro]
        ]
        records.append(struct.pack("<Iiiiiii", offset_us, *axes))
    return b"".join(records)


def _vector_mean(vectors: list[list[int]]) -> list[float]:
    return [statistics.fmean(vector[axis] for vector in vectors) for axis in range(3)]


def _vector_stddev(vectors: list[list[int]]) -> list[float]:
    return [statistics.pstdev(vector[axis] for vector in vectors) for axis in range(3)]


def _round(value: float, digits: int = 12) -> float:
    if not math.isfinite(value):
        raise ImuCalibrationError("calibration produced a non-finite number")
    rounded = round(value, digits)
    return 0.0 if rounded == -0.0 else rounded


def _window_statistics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    accel = [[int(value) for value in sample["accel_mg"]] for sample in samples]
    gyro = [[int(value) for value in sample["gyro_mdps"]] for sample in samples]
    accel_norms = [math.sqrt(sum(component * component for component in vector)) for vector in accel]
    return {
        "accel_mean_mg": [_round(value) for value in _vector_mean(accel)],
        "accel_stddev_mg": [_round(value) for value in _vector_stddev(accel)],
        "accel_norm_mean_mg": _round(statistics.fmean(accel_norms)),
        "accel_norm_stddev_mg": _round(statistics.pstdev(accel_norms)),
        "gyro_mean_mdps": [_round(value) for value in _vector_mean(gyro)],
        "gyro_stddev_mdps": [_round(value) for value in _vector_stddev(gyro)],
    }


def _validate_static_window(stats: dict[str, Any], role: str) -> None:
    norm_mean = stats["accel_norm_mean_mg"]
    norm_stddev = stats["accel_norm_stddev_mg"]
    if not MIN_ACCEL_NORM_MG <= norm_mean <= MAX_ACCEL_NORM_MG:
        raise ImuCalibrationError(f"{role} accel norm mean is not consistent with a static 1 g pose")
    if norm_stddev > MAX_ACCEL_NORM_STDDEV_MG:
        raise ImuCalibrationError(f"{role} accel norm is unstable")
    if any(abs(value) > MAX_STATIC_GYRO_MEAN_MDPS for value in stats["gyro_mean_mdps"]):
        raise ImuCalibrationError(f"{role} gyro mean is not stationary")
    if any(value > MAX_STATIC_GYRO_STDDEV_MDPS for value in stats["gyro_stddev_mdps"]):
        raise ImuCalibrationError(f"{role} gyro signal is unstable")


def _validate_pose_label(stats: dict[str, Any], role: str) -> None:
    axis_index, sign = FACE_EXPECTATIONS[role]
    means = stats["accel_mean_mg"]
    dominant_index = max(range(3), key=lambda index: abs(means[index]))
    if dominant_index != axis_index:
        raise ImuCalibrationError(f"{role} dominant acceleration axis does not match its label")
    if means[axis_index] * sign < MIN_FACE_DOMINANT_MG:
        raise ImuCalibrationError(f"{role} acceleration sign or magnitude does not match its label")
    if any(abs(means[index]) > MAX_FACE_OFF_AXIS_MEAN_MG for index in range(3) if index != axis_index):
        raise ImuCalibrationError(f"{role} off-axis mean is too large for the axis-aligned baseline")


def _validate_source_window(row: dict[str, Any], metadata: dict[str, Any], role: str) -> dict[str, Any]:
    window_id = _text(row.get("window_id"), f"{role}.window_id", pattern=SAFE_ID_RE)
    if window_id != metadata["source_windows"][role]:
        raise ImuCalibrationError(f"{role} window_id does not match metadata")
    if row.get("contract_version") != SOURCE_CONTRACT_VERSION:
        raise ImuCalibrationError(f"{role} is not an {SOURCE_CONTRACT_VERSION} window")
    if row.get("source") != "qmi8658_i2c" or row.get("source_status") != "observed":
        raise ImuCalibrationError(f"{role} must be real observed qmi8658_i2c evidence")
    if row.get("device_id") != metadata["device_id"]:
        raise ImuCalibrationError(f"{role} device_id does not match metadata")
    if row.get("fw_version") != metadata["firmware"]["fw_version"]:
        raise ImuCalibrationError(f"{role} fw_version does not match metadata")
    if row.get("test_run_id") != metadata["test_run_id"]:
        raise ImuCalibrationError(f"{role} test_run_id does not match metadata")
    if row.get("training_allowed") is not False:
        raise ImuCalibrationError(f"{role} must remain training_allowed=false")
    if row.get("capture_time_basis") != "device_monotonic_uptime_only":
        raise ImuCalibrationError(f"{role} must preserve device_monotonic_uptime_only time lineage")

    sensor = _mapping(row.get("sensor"), f"{role}.sensor")
    if (
        sensor.get("model") != metadata["imu_model"]
        or sensor.get("i2c_address") != metadata["sensor_i2c_address"]
        or sensor.get("accel_unit") != "mg"
        or sensor.get("gyro_unit") != "mdps"
    ):
        raise ImuCalibrationError(f"{role} sensor identity or units do not match metadata")

    capture = _mapping(row.get("capture"), f"{role}.capture")
    if (
        capture.get("sample_count") != SAMPLE_COUNT
        or capture.get("requested_interval_us") != REQUESTED_INTERVAL_US
        or capture.get("cadence_quality_status") != "qualified"
        or capture.get("read_failure_count") != 0
        or capture.get("mock_sample_count") != 0
        or type(capture.get("deadline_miss_count")) is not int
        or not 0 <= capture["deadline_miss_count"] <= 5
    ):
        raise ImuCalibrationError(f"{role} capture does not satisfy the fixed real-window quality gate")

    samples = row.get("samples")
    sample_bytes = encode_source_samples(samples, window_id=window_id)
    declared_hash = _text(row.get("samples_sha256"), f"{role}.samples_sha256", pattern=SHA256_RE).lower()
    observed_hash = sha256_hex(sample_bytes)
    if observed_hash != declared_hash:
        raise ImuCalibrationError(f"{role} samples_sha256 does not match the v1 28-byte sample encoding")

    offsets = [int(sample["offset_us"]) for sample in samples]
    intervals = [right - left for left, right in zip(offsets, offsets[1:])]
    observed_cadence = {
        "min_interval_us": min(intervals),
        "mean_interval_us": sum(intervals) // len(intervals),
        "max_interval_us": max(intervals),
    }
    if any(capture.get(key) != value for key, value in observed_cadence.items()):
        raise ImuCalibrationError(f"{role} capture cadence metadata does not match its sample offsets")
    if not (
        40_000 <= observed_cadence["min_interval_us"]
        and observed_cadence["max_interval_us"] <= 60_000
        and 45_000 <= observed_cadence["mean_interval_us"] <= 55_000
    ):
        raise ImuCalibrationError(f"{role} cadence is not compatible with the current 20 Hz contract")
    capture_start = capture.get("capture_start_uptime_us")
    capture_end = capture.get("capture_end_uptime_us")
    if type(capture_start) is not int or type(capture_end) is not int or capture_end <= capture_start:
        raise ImuCalibrationError(f"{role} capture uptime bounds are invalid")
    if offsets[-1] > capture_end - capture_start:
        raise ImuCalibrationError(f"{role} sample offsets exceed capture uptime bounds")

    stats = _window_statistics(samples)
    _validate_static_window(stats, role)
    if role in FACE_EXPECTATIONS:
        _validate_pose_label(stats, role)
    export_hash = row.get("_source_export_sha256")
    if export_hash is None:
        export_hash = sha256_hex(stable_json_bytes({key: value for key, value in row.items() if not key.startswith("_")}))
    export_hash = _text(export_hash, f"{role} source export hash", pattern=SHA256_RE).lower()

    return {
        "role": role,
        "window_id": window_id,
        "capture_cmd_id": _text(row.get("capture_cmd_id"), f"{role}.capture_cmd_id", pattern=SAFE_ID_RE),
        "test_run_id": row["test_run_id"],
        "transport_type": _text(row.get("transport_type"), f"{role}.transport_type"),
        "samples_sha256": declared_hash,
        "source_export_sha256": export_hash,
        "sample_count": SAMPLE_COUNT,
        "capture": {
            "requested_interval_us": REQUESTED_INTERVAL_US,
            **observed_cadence,
            "deadline_miss_count": capture["deadline_miss_count"],
            "capture_start_uptime_us": capture_start,
            "capture_end_uptime_us": capture_end,
        },
        "statistics": stats,
        "samples": samples,
    }


def _calibrated_accel(raw: list[int] | list[float], bias: list[float], gain: list[float]) -> list[float]:
    return [_round((float(raw[index]) - bias[index]) * gain[index]) for index in range(3)]


def _calibrated_gyro(raw: list[int] | list[float], bias: list[float]) -> list[float]:
    return [_round(float(raw[index]) - bias[index]) for index in range(3)]


def _build_estimates(windows: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    face_means = {role: windows[role]["statistics"]["accel_mean_mg"] for role in FACE_ROLES}
    accel_bias: list[float] = []
    sensitivity: list[float] = []
    correction_gain: list[float] = []
    for axis_index, axis in enumerate(AXES):
        positive = face_means[f"{axis}_positive"][axis_index]
        negative = face_means[f"{axis}_negative"][axis_index]
        axis_bias = (positive + negative) / 2.0
        axis_sensitivity = (positive - negative) / 2.0
        if abs(axis_bias) > MAX_ACCEL_BIAS_MG:
            raise ImuCalibrationError(f"{axis} accelerometer bias exceeds the engineering bound")
        if not MIN_SENSITIVITY_MG_PER_G <= axis_sensitivity <= MAX_SENSITIVITY_MG_PER_G:
            raise ImuCalibrationError(f"{axis} accelerometer sensitivity is inconsistent")
        accel_bias.append(_round(axis_bias))
        sensitivity.append(_round(axis_sensitivity))
        correction_gain.append(_round(1000.0 / axis_sensitivity))

    calibrated_face_means: dict[str, list[float]] = {}
    primary_residuals: dict[str, float] = {}
    off_axis_residuals: dict[str, list[float]] = {}
    for role in FACE_ROLES:
        calibrated = _calibrated_accel(face_means[role], accel_bias, correction_gain)
        calibrated_face_means[role] = calibrated
        expected_axis, sign = FACE_EXPECTATIONS[role]
        primary_residual = calibrated[expected_axis] - (1000.0 * sign)
        off_axis = [calibrated[index] for index in range(3) if index != expected_axis]
        primary_residuals[role] = _round(primary_residual)
        off_axis_residuals[role] = [_round(value) for value in off_axis]
    max_primary = max(abs(value) for value in primary_residuals.values())
    max_off_axis = max(abs(value) for values in off_axis_residuals.values() for value in values)
    if max_primary > MAX_PRIMARY_RESIDUAL_MG:
        raise ImuCalibrationError("calibrated face primary-axis residual exceeds the engineering bound")
    if max_off_axis > MAX_OFF_AXIS_RESIDUAL_MG:
        raise ImuCalibrationError("calibrated face off-axis residual exceeds the engineering bound")

    gyro_window = windows[GYRO_ROLE]
    gyro_bias = [_round(value) for value in gyro_window["statistics"]["gyro_mean_mdps"]]
    gyro_stddev = [_round(value) for value in gyro_window["statistics"]["gyro_stddev_mdps"]]

    accelerometer = {
        "method": "opposite_face_diagonal_bias_and_sensitivity_v0.1",
        "axis_order": list(AXES),
        "bias_mg_xyz": accel_bias,
        "sensitivity_mg_per_g_xyz": sensitivity,
        "correction_gain_xyz": correction_gain,
        "face_mean_mg": {role: face_means[role] for role in FACE_ROLES},
        "calibrated_face_mean_mg": calibrated_face_means,
        "residuals": {
            "primary_axis_mg": primary_residuals,
            "off_axis_mg": off_axis_residuals,
            "max_abs_primary_axis_mg": _round(max_primary),
            "max_abs_off_axis_mg": _round(max_off_axis),
        },
    }
    gyroscope = {
        "method": "signed_stationary_mean_bias_v0.1",
        "axis_order": list(AXES),
        "bias_mdps_xyz": gyro_bias,
        "stddev_mdps_xyz": gyro_stddev,
        "source_window_id": gyro_window["window_id"],
        "sample_count": SAMPLE_COUNT,
    }
    return accelerometer, gyroscope


def _materialize_calibrated_windows(
    calibration_id: str,
    calibration_identity_sha256: str,
    windows: dict[str, dict[str, Any]],
    accelerometer: dict[str, Any],
    gyroscope: dict[str, Any],
) -> list[dict[str, Any]]:
    bias_accel = accelerometer["bias_mg_xyz"]
    gain_accel = accelerometer["correction_gain_xyz"]
    bias_gyro = gyroscope["bias_mdps_xyz"]
    output: list[dict[str, Any]] = []
    for role in SOURCE_ROLES:
        source = windows[role]
        samples: list[dict[str, Any]] = []
        for raw_sample in source["samples"]:
            raw_accel = list(raw_sample["accel_mg"])
            raw_gyro = list(raw_sample["gyro_mdps"])
            calibrated_accel = _calibrated_accel(raw_accel, bias_accel, gain_accel)
            calibrated_gyro = _calibrated_gyro(raw_gyro, bias_gyro)
            samples.append(
                {
                    "index": raw_sample["index"],
                    "offset_us": raw_sample["offset_us"],
                    "uncalibrated": {
                        "accel_mg": raw_accel,
                        "gyro_mdps": raw_gyro,
                    },
                    "calibrated": {
                        "accel_mg": calibrated_accel,
                        "gyro_mdps": calibrated_gyro,
                        "accel_m_s2": [_round(value * MG_TO_M_S2) for value in calibrated_accel],
                        "gyro_rad_s": [_round(value * MDPS_TO_RAD_S) for value in calibrated_gyro],
                    },
                }
            )
        output.append(
            {
                "schema_version": CALIBRATED_WINDOW_SCHEMA_VERSION,
                "calibration_id": calibration_id,
                "calibration_identity_sha256": calibration_identity_sha256,
                "role": role,
                "source_window": {
                    "contract_version": SOURCE_CONTRACT_VERSION,
                    "window_id": source["window_id"],
                    "capture_cmd_id": source["capture_cmd_id"],
                    "test_run_id": source["test_run_id"],
                    "transport_type": source["transport_type"],
                    "samples_sha256": source["samples_sha256"],
                    "source_export_sha256": source["source_export_sha256"],
                    "time_basis": "device_monotonic_uptime_only",
                },
                "sample_count": SAMPLE_COUNT,
                "requested_interval_us": REQUESTED_INTERVAL_US,
                "training_allowed": False,
                "production_ready": False,
                "availability": {
                    "adc_counts": "unavailable_in_imu_window_v1",
                    "temperature": "unavailable_in_imu_window_v1",
                    "sample_utc": "unavailable_pending_A0-002",
                },
                "samples": samples,
            }
        )
    return output


def _schema(path: Path) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except FileNotFoundError as error:
        raise ImuCalibrationError(f"required schema is missing: {path}") from error


def validate_outputs(artifact: dict[str, Any], windows: list[dict[str, Any]]) -> None:
    artifact_validator = Draft202012Validator(_schema(ARTIFACT_SCHEMA_PATH))
    calibrated_validator = Draft202012Validator(_schema(CALIBRATED_WINDOW_SCHEMA_PATH))
    artifact_errors = sorted(artifact_validator.iter_errors(artifact), key=lambda error: list(error.path))
    if artifact_errors:
        raise ImuCalibrationError(f"calibration artifact schema validation failed: {artifact_errors[0].message}")
    for index, window in enumerate(windows):
        errors = sorted(calibrated_validator.iter_errors(window), key=lambda error: list(error.path))
        if errors:
            raise ImuCalibrationError(
                f"calibrated window {index} schema validation failed: {errors[0].message}"
            )


def artifact_payload_sha256(artifact: dict[str, Any]) -> str:
    payload = dict(artifact)
    payload.pop("payload_sha256", None)
    return sha256_hex(stable_json_bytes(payload))


def build_calibration_outputs(
    raw_metadata: dict[str, Any],
    raw_windows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], bytes, str]:
    metadata = normalize_metadata(raw_metadata)
    selected_ids = set(metadata["source_windows"].values())
    rows_by_id: dict[str, dict[str, Any]] = {}
    for raw_row in raw_windows:
        row = _mapping(raw_row, "IMU export window")
        window_id = row.get("window_id")
        if not isinstance(window_id, str):
            raise ImuCalibrationError("every IMU export row must have a window_id")
        if window_id in rows_by_id:
            raise ImuCalibrationError(f"duplicate IMU export window_id: {window_id}")
        rows_by_id[window_id] = row
    if set(rows_by_id) != selected_ids:
        missing = sorted(selected_ids - set(rows_by_id))
        extra = sorted(set(rows_by_id) - selected_ids)
        raise ImuCalibrationError(f"IMU export must contain exactly the seven selected windows; missing={missing}, extra={extra}")

    windows = {
        role: _validate_source_window(rows_by_id[metadata["source_windows"][role]], metadata, role)
        for role in SOURCE_ROLES
    }
    command_ids = [windows[role]["capture_cmd_id"] for role in SOURCE_ROLES]
    sample_hashes = [windows[role]["samples_sha256"] for role in SOURCE_ROLES]
    if len(set(command_ids)) != len(command_ids):
        raise ImuCalibrationError("calibration source windows must have unique capture_cmd_id values")
    if len(set(sample_hashes)) != len(sample_hashes):
        raise ImuCalibrationError("calibration source windows must have unique sample hashes")

    accelerometer, gyroscope = _build_estimates(windows)
    source_window_refs = [
        {
            key: windows[role][key]
            for key in (
                "role",
                "window_id",
                "capture_cmd_id",
                "test_run_id",
                "transport_type",
                "samples_sha256",
                "source_export_sha256",
                "sample_count",
            )
        }
        for role in SOURCE_ROLES
    ]
    identity_core = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "estimator_version": ESTIMATOR_VERSION,
        "metadata": metadata,
        "source_windows": source_window_refs,
        "accelerometer": accelerometer,
        "gyroscope": gyroscope,
    }
    identity_sha256 = sha256_hex(stable_json_bytes(identity_core))
    calibration_id = f"imucal-{identity_sha256[:24]}"
    calibrated_windows = _materialize_calibrated_windows(
        calibration_id,
        identity_sha256,
        windows,
        accelerometer,
        gyroscope,
    )
    calibrated_jsonl = b"".join(stable_json_bytes(window) + b"\n" for window in calibrated_windows)
    limitations = [
        "raw_adc_counts_unavailable_in_imu_window_v1",
        "temperature_unavailable_in_imu_window_v1",
        "sample_utc_unavailable_pending_A0-002",
        "diagonal_axis_aligned_calibration_only",
        "cross_axis_misalignment_not_estimated",
        "temperature_drift_not_characterized",
        "final_product_mounting_not_accepted",
        "repeatability_not_yet_established",
        "production_calibration_not_established",
    ]
    artifact: dict[str, Any] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "calibration_id": calibration_id,
        "identity_sha256": identity_sha256,
        "payload_hash_basis": "canonical_json_without_payload_sha256",
        "stage": "engineering",
        "production_ready": False,
        "training_allowed": False,
        "calibration_run_id": metadata["calibration_run_id"],
        "calibration_time_utc": metadata["calibration_time_utc"],
        "calibration_time_source": metadata["calibration_time_source"],
        "device": {
            "device_id": metadata["device_id"],
            "board_id": metadata["board_id"],
            "hardware_revision": metadata["hardware_revision"],
            "hardware_profile": metadata["hardware_profile"],
        },
        "sensor": {
            "imu_model": metadata["imu_model"],
            "imu_module": metadata["imu_module"],
            "sensor_i2c_address": metadata["sensor_i2c_address"],
            "source": "qmi8658_i2c",
            "uncalibrated_accel_unit": "mg",
            "uncalibrated_gyro_unit": "mdps",
        },
        "mounting": {
            "mounting_profile_id": metadata["mounting_profile_id"],
            "calibration_frame": "sensor_axes",
            "body_axis_mapping_status": metadata["body_axis_mapping_status"],
        },
        "firmware": metadata["firmware"],
        "software": {
            "calibration_software_commit": metadata["calibration_software_commit"],
            "estimator_version": ESTIMATOR_VERSION,
        },
        "capture_profile": {
            "source_contract_version": SOURCE_CONTRACT_VERSION,
            "test_run_id": metadata["test_run_id"],
            "sample_count_per_window": SAMPLE_COUNT,
            "requested_interval_us": REQUESTED_INTERVAL_US,
            "current_capture_rate_hz": CURRENT_CAPTURE_RATE_HZ,
            "time_basis": "device_monotonic_uptime_only",
            "face_window_count": len(FACE_ROLES),
            "gyro_window_count": 1,
        },
        "source_exports": [
            {"sha256": digest}
            for digest in sorted({windows[role]["source_export_sha256"] for role in SOURCE_ROLES})
        ],
        "source_windows": source_window_refs,
        "accelerometer": accelerometer,
        "gyroscope": gyroscope,
        "availability": {
            "adc_counts": "unavailable_in_imu_window_v1",
            "temperature": metadata["temperature_status"],
            "sample_utc": "unavailable_pending_A0-002",
        },
        "quality": {
            "passed": True,
            "all_source_hashes_verified": True,
            "all_windows_cadence_qualified": True,
            "all_windows_static": True,
            "all_face_labels_verified": True,
            "thresholds": {
                "accel_norm_mean_mg": [MIN_ACCEL_NORM_MG, MAX_ACCEL_NORM_MG],
                "max_accel_norm_stddev_mg": MAX_ACCEL_NORM_STDDEV_MG,
                "min_face_dominant_mg": MIN_FACE_DOMINANT_MG,
                "max_face_off_axis_mean_mg": MAX_FACE_OFF_AXIS_MEAN_MG,
                "max_static_gyro_mean_mdps": MAX_STATIC_GYRO_MEAN_MDPS,
                "max_static_gyro_stddev_mdps": MAX_STATIC_GYRO_STDDEV_MDPS,
                "sensitivity_mg_per_g": [MIN_SENSITIVITY_MG_PER_G, MAX_SENSITIVITY_MG_PER_G],
                "max_accel_bias_mg": MAX_ACCEL_BIAS_MG,
                "max_primary_residual_mg": MAX_PRIMARY_RESIDUAL_MG,
                "max_off_axis_residual_mg": MAX_OFF_AXIS_RESIDUAL_MG,
            },
        },
        "materialized_output": {
            "schema_version": CALIBRATED_WINDOW_SCHEMA_VERSION,
            "window_count": len(calibrated_windows),
            "sample_count": len(calibrated_windows) * SAMPLE_COUNT,
            "sha256": sha256_hex(calibrated_jsonl),
        },
        "limitations": limitations,
    }
    artifact["payload_sha256"] = artifact_payload_sha256(artifact)
    validate_outputs(artifact, calibrated_windows)
    report = format_report(artifact)
    return artifact, calibrated_windows, calibrated_jsonl, report


def format_report(artifact: dict[str, Any]) -> str:
    accel = artifact["accelerometer"]
    gyro = artifact["gyroscope"]
    source_rows = [
        f"| `{row['role']}` | `{row['window_id']}` | `{row['samples_sha256']}` | `{row['transport_type']}` |"
        for row in artifact["source_windows"]
    ]
    return "\n".join(
        [
            "# A0-001 IMU Engineering Calibration Report",
            "",
            f"- Calibration id: `{artifact['calibration_id']}`",
            f"- Calibration time: `{artifact['calibration_time_utc']}`",
            f"- Calibration time source: `{artifact['calibration_time_source']}`",
            f"- Device: `{artifact['device']['device_id']}`",
            f"- Sensor: `{artifact['sensor']['imu_model']}` / `{artifact['sensor']['imu_module']}`",
            f"- Firmware commit: `{artifact['firmware']['firmware_commit']}`",
            f"- Firmware image SHA-256: `{artifact['firmware']['firmware_image_sha256']}`",
            f"- Stage: `{artifact['stage']}`",
            f"- Production ready: `{artifact['production_ready']}`",
            f"- Training allowed: `{artifact['training_allowed']}`",
            f"- Quality passed: `{artifact['quality']['passed']}`",
            "",
            "## Calibration",
            "",
            f"- Accel bias mg xyz: `{accel['bias_mg_xyz']}`",
            f"- Accel sensitivity mg/g xyz: `{accel['sensitivity_mg_per_g_xyz']}`",
            f"- Accel correction gain xyz: `{accel['correction_gain_xyz']}`",
            f"- Signed gyro bias mdps xyz: `{gyro['bias_mdps_xyz']}`",
            "",
            "## Source Windows",
            "",
            "| Role | Window | Samples SHA-256 | Transport |",
            "|---|---|---|---|",
            *source_rows,
            "",
            "## Preservation Boundary",
            "",
            "The calibrated JSONL preserves each source `accel_mg` and `gyro_mdps`",
            "array exactly under `uncalibrated` and adds calibrated mg/mdps and SI",
            "values. It never overwrites the source IMU export.",
            "",
            "## Limitations",
            "",
            *[f"- `{item}`" for item in artifact["limitations"]],
            "",
            "A passing static pipeline or synthetic fixture is not A0-001 Gate",
            "evidence. A reviewed real six-face plus independent gyro capture is",
            "still required, and A-R0 remains unchanged until that evidence exists.",
            "",
        ]
    )


def write_outputs(
    output_dir: Path,
    artifact: dict[str, Any],
    calibrated_jsonl: bytes,
    report: str,
    *,
    protected_inputs: Iterable[Path] = (),
) -> dict[str, Path]:
    output_dir = output_dir.resolve()
    artifact_path = output_dir / "imu_calibration_artifact.json"
    calibrated_path = output_dir / "imu_calibrated_windows.jsonl"
    report_path = output_dir / "imu_calibration_report.md"
    protected = {path.resolve() for path in protected_inputs}
    if {artifact_path, calibrated_path, report_path} & protected:
        raise ImuCalibrationError("output paths must not overwrite metadata or source IMU exports")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    calibrated_path.write_bytes(calibrated_jsonl)
    report_path.write_text(report, encoding="utf-8")
    return {
        "artifact": artifact_path,
        "calibrated_windows": calibrated_path,
        "report": report_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a fail-closed A0-001 six-face IMU calibration artifact."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--imu-windows", required=True, action="append", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Print the bounded output summary as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metadata = _mapping(json.loads(args.metadata.read_text(encoding="utf-8")), "metadata")
        windows = load_export_windows(args.imu_windows)
        artifact, _calibrated_windows, calibrated_jsonl, report = build_calibration_outputs(metadata, windows)
        outputs = write_outputs(
            args.output_dir,
            artifact,
            calibrated_jsonl,
            report,
            protected_inputs=[args.metadata, *args.imu_windows],
        )
    except (OSError, json.JSONDecodeError, ImuCalibrationError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    summary = {
        "ok": True,
        "calibration_id": artifact["calibration_id"],
        "payload_sha256": artifact["payload_sha256"],
        "production_ready": False,
        "training_allowed": False,
        "hardware_gate_passed": False,
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"generated {artifact['calibration_id']} at {outputs['artifact']}")
        print("hardware_gate_passed=false; A0-001 remains active pending reviewed real capture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
