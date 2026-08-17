from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker


TIME_LINEAGE_VERSION = "egolink.sensor_time_lineage.v0.1"
CLOCK_MAPPING_VERSION = "egolink.clock_mapping_segment.v0.1"
REPORT_VERSION = "egolink.sensor_time_validation_report.v0.1"
MAX_INT64 = 9_223_372_036_854_775_807

SOURCES = ("gnss", "lte", "imu", "camera")
ALIGNMENT_STATUSES = ("unavailable", "receive_only", "estimated", "verified")
FIELD_SOURCE_STATUSES = {"observed", "verified"}
UNIT_NS = {
    "ns": Decimal(1),
    "us": Decimal(1_000),
    "ms": Decimal(1_000_000),
    "s": Decimal(1_000_000_000),
}
SOURCE_SEMANTICS = {
    "gnss": {"measurement_time", "fix_time", "message_time", "unknown"},
    "lte": {"modem_event_time", "message_time", "unknown"},
    "imu": {"sample_time", "capture_start", "message_time", "unknown"},
    "camera": {"exposure_start", "exposure_center", "exposure_end", "unknown"},
}

REPO_ROOT = Path(__file__).resolve().parents[1]
TIME_LINEAGE_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "sensor_time_lineage.schema.json"
CLOCK_MAPPING_SCHEMA_PATH = REPO_ROOT / "shared" / "contracts" / "clock_mapping_segment.schema.json"

UPTIME_MS_RE = re.compile(r"^uptime_ms:(?P<value>[0-9]+)$")
RAW_FRAME_RE = re.compile(r"^raw_frame:(?P<value>[A-Za-z0-9._:-]+)$")
UTC_RE = re.compile(
    r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})T"
    r"(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?P<fraction>[.][0-9]{1,9})?(?P<zone>Z|[+]00:00)$"
)


class SensorTimeLineageError(ValueError):
    """Raised when a lineage input cannot be read or deterministically interpreted."""


def stable_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def parse_utc_ns(value: Any, name: str = "timestamp") -> int:
    if not isinstance(value, str):
        raise SensorTimeLineageError(f"{name} must be a UTC timestamp string")
    match = UTC_RE.fullmatch(value)
    if match is None:
        raise SensorTimeLineageError(
            f"{name} must be ISO-8601 UTC ending in Z or +00:00 with at most 9 fractional digits"
        )
    try:
        base = datetime.strptime(
            f"{match.group('date')}T{match.group('time')}", "%Y-%m-%dT%H:%M:%S"
        ).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise SensorTimeLineageError(f"{name} is not a valid UTC timestamp") from error
    fraction = (match.group("fraction") or "").removeprefix(".")
    fractional_ns = int(fraction.ljust(9, "0")) if fraction else 0
    epoch_seconds = (base - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(seconds=1)
    timestamp_ns = epoch_seconds * 1_000_000_000 + fractional_ns
    if timestamp_ns < 0 or timestamp_ns > MAX_INT64:
        raise SensorTimeLineageError(f"{name} is outside the supported signed-int64 nanosecond range")
    return timestamp_ns


def format_utc_ns(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > MAX_INT64:
        raise SensorTimeLineageError("UTC nanoseconds must be a non-negative integer")
    seconds, fractional_ns = divmod(value, 1_000_000_000)
    base = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    suffix = f".{fractional_ns:09d}".rstrip("0") if fractional_ns else ""
    return base.strftime("%Y-%m-%dT%H:%M:%S") + suffix + "Z"


def classify_legacy_timestamp(value: Any) -> dict[str, Any]:
    """Classify existing `ts` values without silently inventing a clock relationship."""
    if isinstance(value, str):
        uptime = UPTIME_MS_RE.fullmatch(value)
        if uptime is not None:
            milliseconds = int(uptime.group("value"))
            return {
                "kind": "device_monotonic",
                "timestamp_monotonic_ns": milliseconds * 1_000_000,
                "timestamp_utc": None,
                "reason_codes": ["utc_anchor_missing"],
            }
        raw_frame = RAW_FRAME_RE.fullmatch(value)
        if raw_frame is not None:
            return {
                "kind": "opaque_placeholder",
                "timestamp_monotonic_ns": None,
                "timestamp_utc": None,
                "reason_codes": ["source_timestamp_unavailable"],
            }
        try:
            utc_ns = parse_utc_ns(value, "legacy timestamp")
        except SensorTimeLineageError:
            pass
        else:
            return {
                "kind": "ambiguous_iso_utc",
                "timestamp_monotonic_ns": None,
                "timestamp_utc": None,
                "legacy_utc_candidate": format_utc_ns(utc_ns),
                "reason_codes": ["legacy_iso_origin_ambiguous"],
            }
    return {
        "kind": "unrecognized",
        "timestamp_monotonic_ns": None,
        "timestamp_utc": None,
        "reason_codes": ["legacy_timestamp_unrecognized"],
    }


def derive_imu_sample_monotonic_ns(
    capture_start_uptime_us: Any,
    offset_us: Any,
    capture_end_uptime_us: Any | None = None,
) -> int:
    values = (capture_start_uptime_us, offset_us)
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_INT64
        for value in values
    ):
        raise SensorTimeLineageError("IMU capture start and offset must be non-negative integers")
    sample_uptime_us = capture_start_uptime_us + offset_us
    if sample_uptime_us > MAX_INT64 // 1_000:
        raise SensorTimeLineageError("IMU sample timestamp exceeds signed-int64 nanoseconds")
    if capture_end_uptime_us is not None:
        if (
            isinstance(capture_end_uptime_us, bool)
            or not isinstance(capture_end_uptime_us, int)
            or capture_end_uptime_us < capture_start_uptime_us
        ):
            raise SensorTimeLineageError("IMU capture end must not precede capture start")
        if sample_uptime_us > capture_end_uptime_us:
            raise SensorTimeLineageError("IMU sample offset falls after capture end")
    return sample_uptime_us * 1_000


def apply_clock_mapping(mapping: Mapping[str, Any], monotonic_ns: Any) -> int:
    """Map canonical boot-monotonic nanoseconds to UTC without rewriting monotonic time."""
    if (
        isinstance(monotonic_ns, bool)
        or not isinstance(monotonic_ns, int)
        or monotonic_ns < 0
        or monotonic_ns > MAX_INT64
    ):
        raise SensorTimeLineageError("mapped monotonic timestamp must be a non-negative integer")
    start = mapping["valid_from_monotonic_ns"]
    end = mapping["valid_through_monotonic_ns"]
    if monotonic_ns < start or monotonic_ns > end:
        raise SensorTimeLineageError("monotonic timestamp is outside the mapping validity interval")
    drift_multiplier = Decimal(1) + (
        Decimal(str(mapping["utc_rate_correction_ppm"])) / Decimal(1_000_000)
    )
    delta_monotonic_ns = Decimal(monotonic_ns - mapping["monotonic_origin_ns"])
    utc_delta_ns = int(
        (delta_monotonic_ns * drift_multiplier).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    )
    utc_ns = parse_utc_ns(mapping["utc_origin"], "mapping.utc_origin") + utc_delta_ns
    if utc_ns < 0 or utc_ns > MAX_INT64:
        raise SensorTimeLineageError("clock mapping produced a negative timestamp")
    return utc_ns


def source_value_monotonic_ns(source_timestamp: Mapping[str, Any]) -> int:
    value = source_timestamp["raw_value"]
    unit = source_timestamp["unit"]
    if unit not in UNIT_NS:
        raise SensorTimeLineageError("source timestamp is not a numeric monotonic unit")
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_INT64
    ):
        raise SensorTimeLineageError("numeric source timestamp must be a non-negative integer")
    result = int(Decimal(value) * UNIT_NS[unit])
    if result > MAX_INT64:
        raise SensorTimeLineageError("source timestamp conversion exceeds signed-int64 nanoseconds")
    return result


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SensorTimeLineageError(f"cannot load schema {path}: {error}") from error
    if not isinstance(value, dict):
        raise SensorTimeLineageError(f"schema {path} must contain a JSON object")
    return value


def _schema_issues(value: Any, schema: Mapping[str, Any], item_name: str) -> list[dict[str, Any]]:
    if _contains_nonfinite(value):
        return [
            {
                "code": "schema_invalid",
                "item": item_name,
                "path": "",
                "message": "NaN and infinite numeric values are not valid contract data",
            }
        ]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[dict[str, Any]] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path)
        issues.append(
            {
                "code": "schema_invalid",
                "item": item_name,
                "path": path,
                "message": error.message,
            }
        )
    return issues


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonfinite(item) for item in value)
    return False


def _issue(code: str, message: str, *, observation_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if observation_id is not None:
        result["observation_id"] = observation_id
    return result


def _validate_mapping_semantics(mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    mapping_id = str(mapping.get("mapping_id", "unknown"))
    issues: list[dict[str, Any]] = []
    if mapping["valid_from_monotonic_ns"] > mapping["monotonic_origin_ns"]:
        issues.append(_issue("mapping_origin_before_interval", f"{mapping_id}: monotonic origin precedes validity interval"))
    if mapping["monotonic_origin_ns"] > mapping["valid_through_monotonic_ns"]:
        issues.append(_issue("mapping_origin_after_interval", f"{mapping_id}: monotonic origin follows validity interval"))
    anchors = mapping["anchors"]
    if mapping["anchor_count"] != len(anchors):
        issues.append(_issue("mapping_anchor_count_mismatch", f"{mapping_id}: anchor_count does not match anchors"))
    anchor_ids = [anchor["anchor_id"] for anchor in anchors]
    if len(set(anchor_ids)) != len(anchor_ids):
        issues.append(_issue("mapping_anchor_id_duplicate", f"{mapping_id}: anchor ids must be unique"))

    residuals: list[int] = []
    for anchor in anchors:
        try:
            predicted_utc = apply_clock_mapping(mapping, anchor["timestamp_monotonic_ns"])
            observed_utc = parse_utc_ns(anchor["timestamp_utc"], f"{mapping_id}.{anchor['anchor_id']}")
        except SensorTimeLineageError as error:
            issues.append(_issue("mapping_anchor_invalid", f"{mapping_id}: {error}"))
        else:
            residuals.append(abs(predicted_utc - observed_utc))
    if residuals:
        computed_max = max(residuals)
        computed_rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
        if mapping["fit_max_error_ns"] != computed_max:
            issues.append(_issue("mapping_fit_max_mismatch", f"{mapping_id}: declared max fit error does not match anchors"))
        if not math.isclose(mapping["fit_rms_error_ns"], computed_rms, rel_tol=0.0, abs_tol=0.5):
            issues.append(_issue("mapping_fit_rms_mismatch", f"{mapping_id}: declared RMS fit error does not match anchors"))
        required_uncertainty = max(computed_max, *(anchor["uncertainty_ns"] for anchor in anchors))
        if mapping["uncertainty_ns"] < required_uncertainty:
            issues.append(_issue("mapping_uncertainty_too_small", f"{mapping_id}: uncertainty is below anchor/fit error"))
    if mapping["status"] == "verified":
        if mapping["anchor_count"] < 2:
            issues.append(_issue("verified_mapping_needs_two_anchors", f"{mapping_id}: verified mapping needs at least two anchors"))
        if len({anchor["timestamp_monotonic_ns"] for anchor in anchors}) < 2:
            issues.append(_issue("verified_mapping_anchor_span_missing", f"{mapping_id}: verified mapping anchors need a non-zero monotonic span"))
        lineage = mapping["lineage"]
        if lineage["source_status"] not in FIELD_SOURCE_STATUSES:
            issues.append(_issue("verified_mapping_source_unverified", f"{mapping_id}: verified mapping has no observed source"))
    if mapping["lineage"]["evidence_scope"] == "field_session":
        if not mapping["lineage"]["field_session_id"]:
            issues.append(_issue("mapping_field_session_id_missing", f"{mapping_id}: field mapping has no field_session_id"))
        if mapping["lineage"]["firmware_commit"] is None:
            issues.append(_issue("mapping_field_firmware_missing", f"{mapping_id}: field mapping has no firmware_commit"))
    try:
        parse_utc_ns(mapping["utc_origin"], f"{mapping_id}.utc_origin")
        parse_utc_ns(mapping["created_at"], f"{mapping_id}.created_at")
    except SensorTimeLineageError as error:
        issues.append(_issue("mapping_utc_invalid", str(error)))
    return issues


def _validate_record_semantics(
    record: Mapping[str, Any], mappings: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    observation_id = str(record.get("observation_id", "unknown"))
    issues: list[dict[str, Any]] = []
    source = record["source"]
    source_time = record["source_timestamp"]
    alignment = record["alignment"]
    lineage = record["lineage"]
    status = alignment["status"]
    monotonic_origin = alignment["timestamp_monotonic_origin"]
    utc_origin = alignment["timestamp_utc_origin"]

    if source_time["semantics"] not in SOURCE_SEMANTICS[source]:
        issues.append(_issue("source_semantics_invalid", f"{source} cannot use {source_time['semantics']} semantics", observation_id=observation_id))
    if source_time["raw_value"] is None and source_time["unit"] != "unavailable":
        issues.append(_issue("source_value_missing", "null source timestamp must use unit=unavailable", observation_id=observation_id))
    if source_time["raw_value"] is not None and source_time["unit"] == "unavailable":
        issues.append(_issue("source_value_unexpected", "unavailable source timestamp must have null raw_value", observation_id=observation_id))
    if source_time["raw_value"] is not None and source_time["source_field"] is None:
        issues.append(_issue("source_field_missing", "available source timestamp must name its source field", observation_id=observation_id))
    if (
        source_time["raw_value"] is not None
        and source_time["unit"] != "opaque"
        and source_time["clock_domain_id"] is None
    ):
        issues.append(_issue("source_clock_domain_missing", "available timestamp must name its source clock domain", observation_id=observation_id))
    if source_time["raw_value"] is None and (
        source_time["clock_domain_id"] is not None or source_time["source_field"] is not None
    ):
        issues.append(_issue("unavailable_source_provenance_populated", "unavailable source timestamp cannot name a clock or source field", observation_id=observation_id))

    for field in ("timestamp_utc", "receive_timestamp_utc", "ingest_timestamp_utc"):
        value = record[field]
        if value is not None:
            try:
                parse_utc_ns(value, f"{observation_id}.{field}")
            except SensorTimeLineageError as error:
                issues.append(_issue("utc_invalid", str(error), observation_id=observation_id))
    if record["receive_timestamp_utc"] is not None and record["ingest_timestamp_utc"] is not None:
        try:
            receive_ns = parse_utc_ns(
                record["receive_timestamp_utc"], f"{observation_id}.receive_timestamp_utc"
            )
            ingest_ns = parse_utc_ns(
                record["ingest_timestamp_utc"], f"{observation_id}.ingest_timestamp_utc"
            )
        except SensorTimeLineageError:
            pass
        else:
            if ingest_ns < receive_ns:
                issues.append(_issue("ingest_before_receive", "ingest timestamp cannot precede server receive timestamp", observation_id=observation_id))

    if monotonic_origin == "unavailable":
        if (
            record["timestamp_monotonic_ns"] is not None
            or record["monotonic_clock_domain_id"] is not None
            or record["boot_count"] is not None
            or alignment["monotonic_source_field"] is not None
        ):
            issues.append(_issue("monotonic_origin_unavailable_but_populated", "unavailable monotonic origin requires null time/domain/boot/source field", observation_id=observation_id))
    elif monotonic_origin == "source_timestamp":
        if (
            record["monotonic_clock_domain_id"] is None
            or record["boot_count"] is None
            or source_time["clock_domain_id"] != record["monotonic_clock_domain_id"]
            or source_time["source_field"] is None
            or alignment["monotonic_source_field"] != source_time["source_field"]
        ):
            issues.append(_issue("monotonic_source_provenance_mismatch", "source-derived monotonic time needs the same boot clock and source field", observation_id=observation_id))
        try:
            expected_monotonic = source_value_monotonic_ns(source_time)
        except SensorTimeLineageError as error:
            issues.append(_issue("monotonic_source_invalid", str(error), observation_id=observation_id))
        else:
            if record["timestamp_monotonic_ns"] != expected_monotonic:
                issues.append(_issue("monotonic_source_mismatch", "timestamp_monotonic_ns does not equal the raw source counter conversion", observation_id=observation_id))
    elif monotonic_origin == "device_capture":
        if (
            record["timestamp_monotonic_ns"] is None
            or record["monotonic_clock_domain_id"] is None
            or record["boot_count"] is None
            or alignment["monotonic_source_field"] is None
        ):
            issues.append(_issue("device_capture_provenance_missing", "device-captured monotonic time needs time/domain/boot/source field", observation_id=observation_id))

    if utc_origin == "unavailable":
        if record["timestamp_utc"] is not None or alignment["mapping_id"] is not None:
            issues.append(_issue("utc_origin_unavailable_but_populated", "unavailable UTC origin cannot carry timestamp_utc or mapping_id", observation_id=observation_id))
    elif utc_origin == "source_timestamp":
        if alignment["mapping_id"] is not None:
            issues.append(_issue("direct_source_utc_has_mapping", "source UTC origin cannot also name a clock mapping", observation_id=observation_id))
        if source_time["unit"] != "iso8601" or not isinstance(source_time["raw_value"], str):
            issues.append(_issue("direct_source_utc_unparseable", "source UTC origin requires an ISO-8601 raw source timestamp", observation_id=observation_id))
        elif record["timestamp_utc"] is None:
            issues.append(_issue("direct_source_utc_missing", "source UTC origin requires timestamp_utc", observation_id=observation_id))
        else:
            try:
                raw_ns = parse_utc_ns(source_time["raw_value"], f"{observation_id}.source_timestamp")
                normalized_ns = parse_utc_ns(record["timestamp_utc"], f"{observation_id}.timestamp_utc")
                if raw_ns != normalized_ns:
                    issues.append(_issue("direct_source_utc_mismatch", "normalized UTC differs from raw source UTC", observation_id=observation_id))
            except SensorTimeLineageError as error:
                issues.append(_issue("direct_source_utc_invalid", str(error), observation_id=observation_id))
        if (
            source_time["source_field"] is None
            or lineage["source_record_ref"] is None
            or lineage["source_record_sha256"] is None
        ):
            issues.append(_issue("direct_source_utc_provenance_missing", "source UTC must bind its source field and immutable record reference/hash", observation_id=observation_id))
    elif utc_origin == "clock_mapping":
        mapping_id = alignment["mapping_id"]
        if mapping_id is None or mapping_id not in mappings:
            issues.append(_issue("clock_mapping_missing", "clock-mapped UTC references no valid mapping", observation_id=observation_id))
        else:
            mapping = mappings[mapping_id]
            if (
                record["device_id"] != mapping["device_id"]
                or record["monotonic_clock_domain_id"] != mapping["monotonic_clock_domain_id"]
                or record["boot_count"] != mapping["boot_count"]
            ):
                issues.append(_issue("clock_mapping_scope_mismatch", "record device/clock/boot does not match mapping", observation_id=observation_id))
            if lineage["evidence_scope"] == "field_session":
                mapping_lineage = mapping["lineage"]
                if (
                    mapping_lineage["evidence_scope"] != "field_session"
                    or mapping_lineage["field_session_id"] != lineage["field_session_id"]
                    or mapping_lineage["source_status"] not in FIELD_SOURCE_STATUSES
                ):
                    issues.append(_issue("field_mapping_lineage_mismatch", "field observation must use an observed mapping from the same Field Session", observation_id=observation_id))
            try:
                expected_utc = apply_clock_mapping(mapping, record["timestamp_monotonic_ns"])
            except (KeyError, SensorTimeLineageError) as error:
                issues.append(_issue("clock_mapping_application_failed", str(error), observation_id=observation_id))
            else:
                try:
                    actual_utc = parse_utc_ns(record["timestamp_utc"], f"{observation_id}.timestamp_utc")
                except SensorTimeLineageError as error:
                    issues.append(_issue("mapped_utc_invalid", str(error), observation_id=observation_id))
                else:
                    if actual_utc != expected_utc:
                        issues.append(_issue("mapped_utc_mismatch", "timestamp_utc does not match mapping", observation_id=observation_id))
                if alignment["uncertainty_ns"] is not None and alignment["uncertainty_ns"] < mapping["uncertainty_ns"]:
                    issues.append(_issue("record_uncertainty_too_small", "record uncertainty is below mapping uncertainty", observation_id=observation_id))
                if status == "verified" and mapping["status"] != "verified":
                    issues.append(_issue("estimated_mapping_claimed_verified", "estimated mapping cannot produce verified alignment", observation_id=observation_id))
                if source_time["unit"] == "iso8601" and isinstance(source_time["raw_value"], str):
                    try:
                        raw_source_utc = parse_utc_ns(source_time["raw_value"], f"{observation_id}.source_timestamp")
                    except SensorTimeLineageError as error:
                        issues.append(_issue("mapped_source_utc_invalid", str(error), observation_id=observation_id))
                    else:
                        uncertainty = alignment["uncertainty_ns"]
                        if uncertainty is not None and abs(raw_source_utc - expected_utc) > uncertainty:
                            issues.append(_issue("mapped_source_utc_outside_uncertainty", "raw source UTC differs from mapped UTC beyond uncertainty", observation_id=observation_id))

    if status in {"estimated", "verified"}:
        if record["timestamp_monotonic_ns"] is None or record["timestamp_utc"] is None:
            issues.append(_issue("aligned_timestamp_incomplete", "estimated/verified alignment requires monotonic and UTC timestamps", observation_id=observation_id))
        if alignment["uncertainty_ns"] is None:
            issues.append(_issue("alignment_uncertainty_missing", "estimated/verified alignment requires uncertainty_ns", observation_id=observation_id))
        if monotonic_origin == "unavailable":
            issues.append(_issue("aligned_monotonic_origin_missing", "estimated/verified alignment requires traceable monotonic time", observation_id=observation_id))
        if utc_origin != "clock_mapping" or alignment["mapping_id"] is None:
            issues.append(_issue("aligned_clock_mapping_required", "estimated/verified alignment requires a named monotonic-to-UTC mapping", observation_id=observation_id))
    elif status == "receive_only":
        if record["receive_timestamp_utc"] is None:
            issues.append(_issue("receive_timestamp_missing", "receive_only alignment requires receive_timestamp_utc", observation_id=observation_id))
        if record["timestamp_monotonic_ns"] is not None or record["timestamp_utc"] is not None:
            issues.append(_issue("receive_time_promoted", "receive_only record cannot populate source monotonic or UTC time", observation_id=observation_id))
        if (
            alignment["mapping_id"] is not None
            or alignment["uncertainty_ns"] is not None
            or alignment["anchor"] is not None
            or monotonic_origin != "unavailable"
            or utc_origin != "unavailable"
        ):
            issues.append(_issue("receive_only_alignment_claim", "receive_only record cannot carry mapping or uncertainty", observation_id=observation_id))
        if not alignment["reason_codes"]:
            issues.append(_issue("receive_only_reason_missing", "receive_only record requires reason_codes", observation_id=observation_id))
    elif status == "unavailable":
        if not alignment["reason_codes"]:
            issues.append(_issue("unavailable_reason_missing", "unavailable alignment requires reason_codes", observation_id=observation_id))
        if alignment["mapping_id"] is not None or alignment["anchor"] is not None:
            issues.append(_issue("unavailable_alignment_proof_claim", "unavailable alignment cannot claim a mapping or synchronization anchor", observation_id=observation_id))

    if alignment["anchor"] is not None and status != "verified":
        issues.append(_issue("anchor_requires_verified_alignment", "synchronization anchor may only be attached to verified alignment", observation_id=observation_id))

    derivation = record["imu_sample_derivation"]
    if source != "imu" and derivation is not None:
        issues.append(_issue("imu_derivation_on_other_source", "only IMU records may carry imu_sample_derivation", observation_id=observation_id))
    if source == "imu" and source_time["semantics"] == "sample_time":
        if derivation is None:
            issues.append(_issue("imu_derivation_missing", "IMU sample_time requires explicit derivation", observation_id=observation_id))
        else:
            try:
                expected = derive_imu_sample_monotonic_ns(
                    derivation["capture_start_uptime_us"],
                    derivation["offset_us"],
                    derivation["capture_end_uptime_us"],
                )
            except SensorTimeLineageError as error:
                issues.append(_issue("imu_derivation_invalid", str(error), observation_id=observation_id))
            else:
                expected_source_value = derivation["capture_start_uptime_us"] + derivation["offset_us"]
                if source_time["unit"] != "us" or source_time["raw_value"] != expected_source_value:
                    issues.append(_issue("imu_source_time_mismatch", "IMU source timestamp is not capture start plus offset", observation_id=observation_id))
                if record["timestamp_monotonic_ns"] != expected:
                    issues.append(_issue("imu_monotonic_mismatch", "IMU monotonic timestamp does not match start+offset formula", observation_id=observation_id))

    if lineage["evidence_scope"] == "field_session":
        if not lineage["field_session_id"]:
            issues.append(_issue("field_session_id_missing", "field_session evidence must name field_session_id", observation_id=observation_id))
        if lineage["firmware_commit"] is None:
            issues.append(_issue("field_firmware_commit_missing", "field_session evidence must bind firmware_commit", observation_id=observation_id))
        if lineage["source_record_ref"] is None or lineage["source_record_sha256"] is None:
            issues.append(_issue("field_source_evidence_missing", "field_session evidence must bind an immutable source reference/hash", observation_id=observation_id))
    return issues


def _deduplicate(
    values: Iterable[Mapping[str, Any]], id_field: str, conflict_code: str
) -> tuple[list[Mapping[str, Any]], int, list[dict[str, Any]]]:
    unique: list[Mapping[str, Any]] = []
    seen: dict[str, bytes] = {}
    duplicates = 0
    issues: list[dict[str, Any]] = []
    for value in values:
        identifier = str(value[id_field])
        encoded = stable_json_bytes(value)
        if identifier not in seen:
            seen[identifier] = encoded
            unique.append(value)
        elif seen[identifier] == encoded:
            duplicates += 1
        else:
            issues.append(_issue(conflict_code, f"{id_field} {identifier} has conflicting content"))
    return unique, duplicates, issues


def _validate_stream_order(records: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[
            (
                record["device_id"],
                record["source"],
                record["monotonic_clock_domain_id"],
                record["stream_id"],
                record["boot_count"],
            )
        ].append(record)
    for key, rows in groups.items():
        prior_sequence: int | None = None
        prior_monotonic: int | None = None
        prior_utc: int | None = None
        for row in rows:
            sequence = row["sequence_id"]
            if prior_sequence is not None:
                if sequence <= prior_sequence:
                    errors.append(_issue("sequence_not_increasing", f"stream {key} sequence is not strictly increasing", observation_id=row["observation_id"]))
                elif sequence > prior_sequence + 1:
                    warnings.append(_issue("sequence_gap", f"stream {key} sequence gap {prior_sequence}->{sequence}", observation_id=row["observation_id"]))
            prior_sequence = sequence

            monotonic = row["timestamp_monotonic_ns"]
            if monotonic is not None:
                if prior_monotonic is not None and monotonic <= prior_monotonic:
                    errors.append(_issue("monotonic_not_increasing", f"stream {key} monotonic time is not strictly increasing", observation_id=row["observation_id"]))
                prior_monotonic = monotonic

            utc_value = row["timestamp_utc"]
            if utc_value is not None:
                try:
                    utc_ns = parse_utc_ns(utc_value)
                except SensorTimeLineageError:
                    continue
                if prior_utc is not None and utc_ns < prior_utc:
                    errors.append(_issue("utc_time_regression", f"stream {key} UTC time regressed", observation_id=row["observation_id"]))
                prior_utc = utc_ns
    return errors, warnings


def _alignment_analysis(
    records: Iterable[Mapping[str, Any]],
    mappings: Mapping[str, Mapping[str, Any]],
    required_sources: tuple[str, ...],
) -> dict[str, Any]:
    anchors: dict[tuple[Any, str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        alignment = record["alignment"]
        session_id = record["lineage"]["field_session_id"]
        anchor = alignment["anchor"]
        mapping = mappings.get(alignment["mapping_id"])
        if (
            alignment["status"] == "verified"
            and alignment["timestamp_utc_origin"] == "clock_mapping"
            and mapping is not None
            and mapping["status"] == "verified"
            and mapping["lineage"]["evidence_scope"] == "field_session"
            and mapping["lineage"]["field_session_id"] == session_id
            and mapping["lineage"]["source_status"] in FIELD_SOURCE_STATUSES
            and anchor is not None
            and record["timestamp_utc"] is not None
            and record["lineage"]["evidence_scope"] == "field_session"
            and record["lineage"]["source_status"] in FIELD_SOURCE_STATUSES
            and record["lineage"]["source_record_ref"] is not None
            and record["lineage"]["source_record_sha256"] is not None
            and session_id is not None
        ):
            anchors[
                (
                    session_id,
                    anchor["anchor_id"],
                    anchor["method"],
                    anchor["evidence_ref"],
                    anchor["evidence_sha256"],
                )
            ].append(record)

    qualifying: list[dict[str, Any]] = []
    required = set(required_sources)
    for (session_id, anchor_id, method, evidence_ref, evidence_sha256), rows in anchors.items():
        present_sources = {row["source"] for row in rows}
        if not required.issubset(present_sources):
            continue
        relevant_rows = [row for row in rows if row["source"] in required]
        timestamp_pairs = [
            (parse_utc_ns(row["timestamp_utc"]), row["alignment"]["uncertainty_ns"])
            for row in relevant_rows
        ]
        observed_span_ns = max(value for value, _ in timestamp_pairs) - min(
            value for value, _ in timestamp_pairs
        )
        conservative_bound_ns = max(
            abs(left_time - right_time) + left_uncertainty + right_uncertainty
            for index, (left_time, left_uncertainty) in enumerate(timestamp_pairs)
            for right_time, right_uncertainty in timestamp_pairs[index + 1 :]
        )
        qualifying.append(
            {
                "field_session_id": session_id,
                "anchor_id": anchor_id,
                "method": method,
                "evidence_ref": evidence_ref,
                "evidence_sha256": evidence_sha256,
                "sources": list(required_sources),
                "observed_span_ns": observed_span_ns,
                "conservative_bound_ns": conservative_bound_ns,
            }
        )
    if not qualifying:
        return {
            "status": "unavailable",
            "reason": "no_common_verified_anchor_for_all_required_sources",
            "common_verified_anchors": [],
            "max_observed_anchor_span_ns": None,
            "max_conservative_alignment_bound_ns": None,
        }
    return {
        "status": "available",
        "reason": None,
        "common_verified_anchors": qualifying,
        "max_observed_anchor_span_ns": max(item["observed_span_ns"] for item in qualifying),
        "max_conservative_alignment_bound_ns": max(
            item["conservative_bound_ns"] for item in qualifying
        ),
    }


def validate_time_lineage(
    records: Iterable[Mapping[str, Any]],
    mappings: Iterable[Mapping[str, Any]] = (),
    *,
    required_sources: Iterable[str] = SOURCES,
    generated_at: str | None = None,
) -> dict[str, Any]:
    required = tuple(dict.fromkeys(required_sources))
    unknown_sources = sorted(set(required) - set(SOURCES))
    if unknown_sources:
        raise SensorTimeLineageError(f"unknown required sources: {unknown_sources}")
    generated = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    parse_utc_ns(generated, "generated_at")

    record_schema = _load_schema(TIME_LINEAGE_SCHEMA_PATH)
    mapping_schema = _load_schema(CLOCK_MAPPING_SCHEMA_PATH)
    record_values = list(records)
    mapping_values = list(mappings)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    schema_valid_mappings: list[Mapping[str, Any]] = []
    for index, mapping in enumerate(mapping_values):
        issues = _schema_issues(mapping, mapping_schema, f"mapping[{index}]")
        errors.extend(issues)
        if not issues:
            schema_valid_mappings.append(mapping)
    unique_mappings, duplicate_mappings, duplicate_mapping_errors = _deduplicate(
        schema_valid_mappings, "mapping_id", "mapping_id_conflict"
    )
    errors.extend(duplicate_mapping_errors)
    mapping_index = {mapping["mapping_id"]: mapping for mapping in unique_mappings}
    semantically_valid_mappings: dict[str, Mapping[str, Any]] = {}
    for mapping in unique_mappings:
        mapping_issues = _validate_mapping_semantics(mapping)
        errors.extend(mapping_issues)
        if not mapping_issues:
            semantically_valid_mappings[mapping["mapping_id"]] = mapping

    schema_valid_records: list[Mapping[str, Any]] = []
    for index, record in enumerate(record_values):
        issues = _schema_issues(record, record_schema, f"record[{index}]")
        errors.extend(issues)
        if not issues:
            schema_valid_records.append(record)
    unique_records, duplicate_records, duplicate_record_errors = _deduplicate(
        schema_valid_records, "observation_id", "observation_id_conflict"
    )
    errors.extend(duplicate_record_errors)
    if duplicate_records:
        warnings.append(_issue("idempotent_duplicates_ignored", f"ignored {duplicate_records} byte-equivalent duplicate observations"))
    if duplicate_mappings:
        warnings.append(_issue("idempotent_mapping_duplicates_ignored", f"ignored {duplicate_mappings} byte-equivalent duplicate mappings"))

    semantically_valid_records: list[Mapping[str, Any]] = []
    for record in unique_records:
        record_issues = _validate_record_semantics(record, mapping_index)
        errors.extend(record_issues)
        if not record_issues:
            semantically_valid_records.append(record)
    order_errors, order_warnings = _validate_stream_order(semantically_valid_records)
    errors.extend(order_errors)
    warnings.extend(order_warnings)

    coverage: dict[str, Any] = {}
    for source in SOURCES:
        rows = [record for record in unique_records if record["source"] == source]
        coverage[source] = {
            "record_count": len(rows),
            "alignment_status_counts": {
                status: sum(1 for row in rows if row["alignment"]["status"] == status)
                for status in ALIGNMENT_STATUSES
            },
            "monotonic_present_count": sum(row["timestamp_monotonic_ns"] is not None for row in rows),
            "utc_present_count": sum(row["timestamp_utc"] is not None for row in rows),
            "field_record_count": sum(row["lineage"]["evidence_scope"] == "field_session" for row in rows),
        }

    alignment_analysis = _alignment_analysis(
        semantically_valid_records, semantically_valid_mappings, SOURCES
    )
    requested_missing_sources = [
        source for source in required if not any(record["source"] == source for record in unique_records)
    ]
    field_reasons: list[str] = []
    if errors:
        field_reasons.append("validation_errors_present")
    for source in SOURCES:
        rows = [record for record in semantically_valid_records if record["source"] == source]
        if not rows:
            field_reasons.append(f"required_source_missing:{source}")
            continue
        qualifying = [
            record
            for record in rows
            if record["lineage"]["evidence_scope"] == "field_session"
            and record["lineage"]["source_status"] in FIELD_SOURCE_STATUSES
            and record["lineage"]["field_session_id"] is not None
            and record["lineage"]["source_record_ref"] is not None
            and record["lineage"]["source_record_sha256"] is not None
            and record["lineage"]["firmware_commit"] is not None
            and record["boot_count"] is not None
            and record["monotonic_clock_domain_id"] is not None
            and record["timestamp_monotonic_ns"] is not None
            and record["timestamp_utc"] is not None
            and record["alignment"]["status"] == "verified"
            and record["source_timestamp"]["semantics"] != "unknown"
            and record["alignment"]["timestamp_utc_origin"] == "clock_mapping"
            and record["alignment"]["mapping_id"] in semantically_valid_mappings
            and semantically_valid_mappings[record["alignment"]["mapping_id"]]["status"] == "verified"
            and semantically_valid_mappings[record["alignment"]["mapping_id"]]["lineage"]["evidence_scope"] == "field_session"
            and semantically_valid_mappings[record["alignment"]["mapping_id"]]["lineage"]["field_session_id"] == record["lineage"]["field_session_id"]
            and semantically_valid_mappings[record["alignment"]["mapping_id"]]["lineage"]["source_status"] in FIELD_SOURCE_STATUSES
        ]
        if not qualifying:
            field_reasons.append(f"verified_field_lineage_missing:{source}")
    session_ids = {
        record["lineage"]["field_session_id"]
        for record in semantically_valid_records
        if record["source"] in SOURCES
        and record["lineage"]["evidence_scope"] == "field_session"
        and record["lineage"]["field_session_id"] is not None
    }
    if len(session_ids) != 1:
        field_reasons.append("single_field_session_not_established")
    if alignment_analysis["status"] != "available":
        field_reasons.append("alignment_bound_unavailable")

    return {
        "report_version": REPORT_VERSION,
        "generated_at": generated,
        "valid": not errors,
        "input": {
            "record_count": len(record_values),
            "unique_record_count": len(unique_records),
            "idempotent_duplicate_count": duplicate_records,
            "mapping_count": len(mapping_values),
            "unique_mapping_count": len(unique_mappings),
            "required_sources": list(required),
            "requested_coverage_complete": not requested_missing_sources,
            "requested_missing_sources": requested_missing_sources,
        },
        "coverage": coverage,
        "alignment": alignment_analysis,
        "field_eligible": not field_reasons,
        "field_eligibility_reasons": list(dict.fromkeys(field_reasons)),
        "gate_status": "unverified",
        "gate_reason": "requires reviewed real four-source Field Session evidence and a frozen acceptance threshold",
        "errors": errors,
        "warnings": warnings,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise SensorTimeLineageError(f"cannot read {path}: {error}") from error
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(
                line,
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant {constant}")
                ),
            )
        except (json.JSONDecodeError, ValueError) as error:
            message = error.msg if isinstance(error, json.JSONDecodeError) else str(error)
            raise SensorTimeLineageError(f"{path}:{line_number}: invalid JSON: {message}") from error
        if not isinstance(value, dict):
            raise SensorTimeLineageError(f"{path}:{line_number}: expected a JSON object")
        values.append(value)
    return values


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise SensorTimeLineageError(f"cannot write {path}: {error}") from error


def parse_sources(value: str) -> tuple[str, ...]:
    sources = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(sources) - set(SOURCES))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown sources: {', '.join(unknown)}")
    return tuple(dict.fromkeys(sources))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Ego Link A0-002 sensor time lineage JSONL")
    parser.add_argument("records", type=Path, help="normalized sensor time lineage JSONL")
    parser.add_argument("--mappings", type=Path, help="optional clock mapping segment JSONL")
    parser.add_argument(
        "--required-sources",
        type=parse_sources,
        default=SOURCES,
        help="comma-separated coverage set (default: gnss,lte,imu,camera)",
    )
    parser.add_argument("--output", type=Path, help="write the machine-readable report here")
    parser.add_argument(
        "--fail-if-ineligible",
        action="store_true",
        help="exit 1 when the input is valid but not eligible as a real four-source Field Session",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        records = load_jsonl(args.records)
        mappings = load_jsonl(args.mappings) if args.mappings else []
        report = validate_time_lineage(
            records,
            mappings,
            required_sources=args.required_sources,
        )
        if args.output:
            write_json(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except SensorTimeLineageError as error:
        print(f"A0-002 input error: {error}", file=sys.stderr)
        return 2
    if not report["valid"]:
        return 1
    if args.fail_if_ineligible and not report["field_eligible"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
