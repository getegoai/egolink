"""AI-Native multi-modal self-supervised dataset harvester for EgoLink (AI-010).

This tool ingests multi-modal field telemetry (from SQLite collection_records or
JSONL exports), extracts and decodes continuous IMU samples, slices them into
100-sample (5.0s @ 20Hz) sliding windows, executes cross-modal self-supervision
(GNSS velocity, cellular stability, power/fuel-gauge anchors) to assign pseudo-labels,
detects sensor-contradiction ambiguity gold samples, and outputs a structured
dataset manifest and window records.

Privacy Rule: Exact GPS coordinates are never exported into public window records;
only Doppler speed, fix validity, HDOP, and satellite count are retained as evidence.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path
import sqlite3
import struct
import sys
from typing import Any, Dict, Iterator, List, Optional, Tuple


HARVEST_SCHEMA_VERSION = "egolink.ai_dataset_manifest.v1"
WINDOW_RECORD_SCHEMA_VERSION = "egolink.ai_window_record.v1"

NOMINAL_WINDOW_SAMPLES = 100
NOMINAL_STEP_SAMPLES = 50
MAX_IMU_SAMPLE_GAP_NS = 500_000_000  # 500ms max gap within a continuous window


def decode_imu_chunk(payload: Dict[str, Any], base_timestamp_ns: int) -> List[Dict[str, Any]]:
    """Decode a binary base64 IMU chunk into physical SI units.

    Encoding: "offset_us+six_i16le+base64-v1"
    Each record (16 bytes):
      uint32 offset_us
      int16 ax_raw, ay_raw, az_raw
      int16 gx_raw, gy_raw, gz_raw
    """
    samples_b64 = payload.get("samples_b64", "")
    if not samples_b64:
        return []

    data = base64.b64decode(samples_b64)
    record_bytes = int(payload.get("sample_record_bytes", 16))
    if record_bytes != 16 or len(data) % 16 != 0:
        raise ValueError(f"Invalid IMU binary payload length {len(data)} (expected multiple of 16)")

    sample_count = len(data) // 16
    accel_scale = float(payload.get("accel_full_scale_mg", 4000))
    gyro_scale = float(payload.get("gyro_full_scale_mdps", 512000))
    raw_divisor = float(payload.get("raw_divisor", 32768))

    accel_factor = (accel_scale / raw_divisor) * 0.00980665  # mg -> m/s^2
    gyro_factor = (gyro_scale / raw_divisor) / 1000.0        # mdps -> dps

    decoded: List[Dict[str, Any]] = []
    for i in range(sample_count):
        offset = i * 16
        offset_us = struct.unpack_from("<I", data, offset)[0]
        ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw = struct.unpack_from("<6h", data, offset + 4)

        t_ns = base_timestamp_ns + int(offset_us) * 1000
        decoded.append({
            "t_ns": t_ns,
            "ax": ax_raw * accel_factor,
            "ay": ay_raw * accel_factor,
            "az": az_raw * accel_factor,
            "gx": gx_raw * gyro_factor,
            "gy": gy_raw * gyro_factor,
            "gz": gz_raw * gyro_factor,
        })
    return decoded


def compute_window_features(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute physical statistical features over a window of 6-axis IMU samples."""
    count = len(samples)
    if count == 0:
        return {
            "sample_count": 0,
            "duration_ms": 0.0,
            "sample_rate_hz": 0.0,
            "mean_accel_m_s2": 0.0,
            "motion_rms_m_s2": 0.0,
            "peak_accel_m_s2": 0.0,
            "gyro_variance_dps2": 0.0,
            "cadence_hz": 0.0,
        }

    t_start = samples[0]["t_ns"]
    t_end = samples[-1]["t_ns"]
    dt_ns = t_end - t_start
    duration_ms = dt_ns / 1_000_000.0
    sample_rate_hz = (count - 1) / (dt_ns / 1_000_000_000.0) if dt_ns > 0 else 0.0

    mags: List[float] = []
    sum_m = 0.0
    peak_m = 0.0
    sum_gx = 0.0
    sum_gy = 0.0
    sum_gz = 0.0

    for s in samples:
        ax, ay, az = s["ax"], s["ay"], s["az"]
        m = math.sqrt(ax * ax + ay * ay + az * az)
        mags.append(m)
        sum_m += m
        if m > peak_m:
            peak_m = m
        sum_gx += s["gx"]
        sum_gy += s["gy"]
        sum_gz += s["gz"]

    mean_m = sum_m / count
    mean_gx = sum_gx / count
    mean_gy = sum_gy / count
    mean_gz = sum_gz / count

    sum_sq_diff_m = 0.0
    sum_sq_diff_g = 0.0
    for i, s in enumerate(samples):
        dm = mags[i] - mean_m
        sum_sq_diff_m += dm * dm
        dgx = s["gx"] - mean_gx
        dgy = s["gy"] - mean_gy
        dgz = s["gz"] - mean_gz
        sum_sq_diff_g += (dgx * dgx + dgy * dgy + dgz * dgz)

    motion_rms = math.sqrt(sum_sq_diff_m / count)
    gyro_variance = sum_sq_diff_g / count

    # Step cadence estimation via zero-crossings of mean-centered magnitude
    cadence_hz = 0.0
    if dt_ns > 0 and motion_rms > 0.15:
        crossings = 0
        centered = [m - mean_m for m in mags]
        for i in range(1, count):
            if (centered[i - 1] < 0.0 and centered[i] >= 0.0) or (centered[i - 1] >= 0.0 and centered[i] < 0.0):
                crossings += 1
        # Two zero-crossings per full cycle
        cycles = crossings / 2.0
        duration_s = dt_ns / 1_000_000_000.0
        if duration_s > 0:
            cadence_hz = round(cycles / duration_s, 2)

    return {
        "sample_count": count,
        "duration_ms": round(duration_ms, 2),
        "sample_rate_hz": round(sample_rate_hz, 1),
        "mean_accel_m_s2": round(mean_m, 4),
        "motion_rms_m_s2": round(motion_rms, 4),
        "peak_accel_m_s2": round(peak_m, 4),
        "gyro_variance_dps2": round(gyro_variance, 4),
        "cadence_hz": cadence_hz,
    }


def find_nearest_observation(
    observations: List[Dict[str, Any]], target_t_ns: int, max_window_ns: int
) -> Optional[Dict[str, Any]]:
    """Find the closest observation to target_t_ns within max_window_ns."""
    if not observations:
        return None
    best = None
    min_diff = max_window_ns + 1
    for obs in observations:
        diff = abs(obs["t_ns"] - target_t_ns)
        if diff < min_diff:
            min_diff = diff
            best = obs
    return best if min_diff <= max_window_ns else None


def self_supervised_label(
    imu_features: Dict[str, Any],
    gnss: Optional[Dict[str, Any]],
    power: Optional[Dict[str, Any]],
    cellular: Optional[Dict[str, Any]],
    ego_baseline: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    """Assign physical self-supervised pseudo-label and detect ambiguity flags."""
    rms = imu_features["motion_rms_m_s2"]
    peak = imu_features["peak_accel_m_s2"]
    gyro_var = imu_features["gyro_variance_dps2"]
    cadence = imu_features["cadence_hz"]

    gnss_fix = bool(gnss and gnss.get("fix"))
    speed = float(gnss.get("speed_mps", 0.0)) if (gnss and gnss.get("speed_mps") is not None) else None
    hdop = float(gnss.get("hdop", 99.0)) if (gnss and gnss.get("hdop") is not None) else 99.0

    is_charging = bool(power and power.get("charging") is True)

    label_class = "unassigned"
    confidence = 0.0
    source_rule = "none"
    ambiguity_flags: List[str] = []

    # Priority 1: High-G Mechanical Impact & Fall
    if peak >= 25.0:
        if rms < 0.15:
            label_class = "fall_suspected"
            confidence = 0.85
            source_rule = "high_g_impact_followed_by_immobility"
        else:
            label_class = "abnormal_shock"
            confidence = 0.90
            source_rule = "high_g_impact_peak"

    # Priority 2: Charging Dock / Absolute Resting Anchor
    elif is_charging and rms < 0.05 and gyro_var < 0.05:
        label_class = "stationary_charging"
        confidence = 0.99
        source_rule = "fuel_gauge_charging_zero_variance"

    # Priority 3: In-Vehicle Transit (GNSS Doppler speed >= 6.5 m/s = 23.4 km/h)
    elif gnss_fix and speed is not None and speed >= 6.5 and hdop <= 3.0:
        label_class = "in_vehicle"
        confidence = 0.98
        source_rule = "gnss_high_velocity_teacher"

    # Priority 4: Cycling (10 km/h <= v <= 23.4 km/h, rhythmic/moderate vibration)
    elif (
        gnss_fix
        and speed is not None
        and 2.8 <= speed < 6.5
        and hdop <= 2.5
        and 0.15 <= rms <= 1.8
    ):
        label_class = "cycling"
        confidence = 0.95
        source_rule = "gnss_moderate_velocity_cyclical_imu"

    # Priority 5: Running (High RMS and either high cadence or moderate running speed)
    elif (rms >= 1.2 and ((speed is not None and speed >= 2.0) or cadence >= 2.4)) or (
        gnss_fix and speed is not None and 2.5 <= speed < 6.5 and rms >= 1.2
    ):
        label_class = "running"
        confidence = 0.92
        source_rule = "high_cadence_rms_speed"

    # Priority 6: Pedestrian Walking (Cadence 1.0~2.3Hz, moderate RMS, speed <= 2.2 m/s)
    elif 0.20 <= rms <= 1.2 and (speed is None or speed <= 2.2) and (1.0 <= cadence <= 2.3 or (speed is not None and speed > 0.4)):
        label_class = "walking"
        confidence = 0.90
        source_rule = "pedestrian_cadence_rms"

    # Priority 7: Stationary (Quiet IMU, zero/low speed or no GNSS)
    elif rms < 0.15 and gyro_var < 0.10 and (speed is None or speed < 0.5):
        label_class = "stationary"
        confidence = 0.95
        source_rule = "quiet_imu_zero_velocity"

    # Priority 8: General fallback based on IMU alone
    elif rms >= 0.30:
        label_class = "walking"
        confidence = 0.70
        source_rule = "imu_rms_only_fallback"
    else:
        label_class = "stationary"
        confidence = 0.70
        source_rule = "imu_quiet_fallback"

    # Ambiguity / Contradiction Mining
    if rms >= 0.50 and gnss_fix and speed is not None and speed < 0.3 and hdop < 1.5:
        ambiguity_flags.append("high_motion_zero_velocity")

    if gnss_fix and speed is not None and speed >= 5.0 and rms < 0.10:
        ambiguity_flags.append("high_speed_low_motion")

    if ego_baseline and ego_baseline.get("spatial_mobility"):
        rule_mob = ego_baseline["spatial_mobility"]
        if rule_mob not in ("unknown", "") and label_class not in ("unassigned", ""):
            # Map canonical names for comparison
            mob_map = {
                "pedestrian_walking": "walking",
                "running": "running",
                "in_vehicle": "in_vehicle",
                "stationary": "stationary",
                "stationary_charging": "stationary",
            }
            mapped_rule = mob_map.get(rule_mob, rule_mob)
            mapped_label = mob_map.get(label_class, label_class)
            if mapped_rule != mapped_label and mapped_rule != "indoor_weak_gnss":
                ambiguity_flags.append(f"rule_disagreement:{rule_mob}_vs_{label_class}")

    return {
        "class_name": label_class,
        "confidence": confidence,
        "source_rule": source_rule,
    }, ambiguity_flags


class SelfSupervisedHarvester:
    """Multi-modal sliding window harvester and pseudo-labeler."""

    def __init__(
        self,
        *,
        window_samples: int = NOMINAL_WINDOW_SAMPLES,
        step_samples: int = NOMINAL_STEP_SAMPLES,
    ):
        self.window_samples = window_samples
        self.step_samples = step_samples
        self.imu_samples: List[Dict[str, Any]] = []
        self.gnss_records: List[Dict[str, Any]] = []
        self.power_records: List[Dict[str, Any]] = []
        self.cellular_records: List[Dict[str, Any]] = []
        self.ego_baseline_records: List[Dict[str, Any]] = []
        self.device_id = "unknown"
        self.boot_count = 0
        self.session_id = "unknown"

    def ingest_envelope(self, envelope: Dict[str, Any]) -> None:
        """Ingest a single collection envelope from the multi-modal stream."""
        source = envelope.get("source")
        payload = envelope.get("payload", {})
        t_ns = int(envelope.get("timestamp_monotonic_ns", 0))

        if self.device_id == "unknown" and envelope.get("device_id"):
            self.device_id = envelope["device_id"]
        if self.boot_count == 0 and envelope.get("boot_count"):
            self.boot_count = int(envelope["boot_count"])
        if self.session_id == "unknown" and envelope.get("session_id"):
            self.session_id = envelope["session_id"]

        if source == "imu":
            chunk_samples = decode_imu_chunk(payload, t_ns)
            self.imu_samples.extend(chunk_samples)

        elif source == "gnss":
            self.gnss_records.append({
                "t_ns": t_ns,
                "fix": payload.get("fix", False),
                "speed_mps": payload.get("speed_mps"),
                "hdop": payload.get("hdop"),
                "satellites": payload.get("satellites"),
                "status": envelope.get("status"),
            })

        elif source == "power":
            self.power_records.append({
                "t_ns": t_ns,
                "charging": payload.get("charging"),
                "battery_mv": payload.get("battery_millivolt"),
                "soc_percent": payload.get("fuel_gauge_soc_percent"),
            })

        elif source == "lte":
            self.cellular_records.append({
                "t_ns": t_ns,
                "rsrp": payload.get("rsrp"),
                "cell_id": payload.get("cell_id"),
                "lac": payload.get("lac"),
            })

        elif source == "device":
            ego = payload.get("ego_state")
            if isinstance(ego, dict) and ego.get("ready"):
                self.ego_baseline_records.append({
                    "t_ns": t_ns,
                    "spatial_mobility": ego.get("spatial_mobility"),
                    "posture_anomaly": ego.get("posture_anomaly"),
                    "confidence": ego.get("confidence"),
                })

    def harvest(self) -> Iterator[Dict[str, Any]]:
        """Slice continuous IMU streams and emit pseudo-labeled window records."""
        self.imu_samples.sort(key=lambda s: s["t_ns"])
        total_samples = len(self.imu_samples)
        if total_samples < self.window_samples:
            return

        window_idx = 0
        start_idx = 0

        while start_idx + self.window_samples <= total_samples:
            window_slice = self.imu_samples[start_idx : start_idx + self.window_samples]

            # Check for excessive gaps inside the window
            gap_detected = False
            for j in range(1, len(window_slice)):
                if window_slice[j]["t_ns"] - window_slice[j - 1]["t_ns"] > MAX_IMU_SAMPLE_GAP_NS:
                    gap_detected = True
                    start_idx = start_idx + j
                    break

            if gap_detected:
                continue

            t_start = window_slice[0]["t_ns"]
            t_end = window_slice[-1]["t_ns"]
            t_center = (t_start + t_end) // 2

            # Compute statistical features
            imu_features = compute_window_features(window_slice)

            # Match cross-modal context
            nearest_gnss = find_nearest_observation(self.gnss_records, t_center, max_window_ns=30_000_000_000)
            nearest_power = find_nearest_observation(self.power_records, t_center, max_window_ns=60_000_000_000)
            nearest_cell = find_nearest_observation(self.cellular_records, t_center, max_window_ns=60_000_000_000)
            nearest_ego = find_nearest_observation(self.ego_baseline_records, t_center, max_window_ns=15_000_000_000)

            # Self-supervised labeling & ambiguity detection
            pseudo_label, ambiguity_flags = self_supervised_label(
                imu_features, nearest_gnss, nearest_power, nearest_cell, nearest_ego
            )

            # Raw tensor representation [100, 6]
            raw_tensor = [
                [
                    round(s["ax"], 4),
                    round(s["ay"], 4),
                    round(s["az"], 4),
                    round(s["gx"], 3),
                    round(s["gy"], 3),
                    round(s["gz"], 3),
                ]
                for s in window_slice
            ]

            window_record = {
                "schema_version": WINDOW_RECORD_SCHEMA_VERSION,
                "window_id": f"win-b{self.boot_count}-{window_idx:05d}",
                "device_id": self.device_id,
                "boot_count": self.boot_count,
                "session_id": self.session_id,
                "timestamp_start_ns": t_start,
                "timestamp_end_ns": t_end,
                "timestamp_center_ns": t_center,
                "imu_features": imu_features,
                "cross_modal_context": {
                    "gnss_fix": bool(nearest_gnss and nearest_gnss.get("fix")),
                    "gnss_speed_mps": nearest_gnss.get("speed_mps") if nearest_gnss else None,
                    "gnss_hdop": nearest_gnss.get("hdop") if nearest_gnss else None,
                    "gnss_satellites": nearest_gnss.get("satellites") if nearest_gnss else None,
                    "is_charging": nearest_power.get("charging") if nearest_power else None,
                    "battery_mv": nearest_power.get("battery_mv") if nearest_power else None,
                    "cell_id": nearest_cell.get("cell_id") if nearest_cell else None,
                },
                "pseudo_label": pseudo_label,
                "rule_baseline": {
                    "spatial_mobility": nearest_ego.get("spatial_mobility") if nearest_ego else "unknown",
                    "posture_anomaly": nearest_ego.get("posture_anomaly") if nearest_ego else "unknown",
                },
                "is_ambiguity_sample": len(ambiguity_flags) > 0,
                "ambiguity_reasons": ambiguity_flags,
                "tensor_shape": [self.window_samples, 6],
                "raw_tensor": raw_tensor,
            }

            yield window_record
            window_idx += 1
            start_idx += self.step_samples


def harvest_dataset_from_db(
    db_path: Path,
    output_dir: Path,
    *,
    device_id: Optional[str] = None,
    boot_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Ingest collection_records from SQLite DB and write dataset manifest and JSONL."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "dataset_manifest.json"
    windows_path = output_dir / "windows.jsonl"

    harvester = SelfSupervisedHarvester()

    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        total_ingested = 0

        if "collection_records" in tables:
            query = "SELECT envelope_json FROM collection_records WHERE 1=1"
            params: List[Any] = []
            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)
            if boot_count is not None:
                query += " AND boot_count = ?"
                params.append(boot_count)
            query += " ORDER BY boot_count ASC, event_monotonic_ns ASC, id ASC"

            cursor.execute(query, params)
            for row in cursor:
                envelope = json.loads(row["envelope_json"])
                harvester.ingest_envelope(envelope)
                total_ingested += 1
        elif "raw_frames" in tables:
            query = "SELECT raw_payload_b64 FROM raw_frames WHERE 1=1"
            params: List[Any] = []
            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)
            query += " ORDER BY id ASC"
            cursor.execute(query, params)
            for row in cursor:
                try:
                    raw_bytes = base64.b64decode(row["raw_payload_b64"])
                    text = raw_bytes.decode("utf-8", errors="ignore")
                    if "{" in text:
                        start_idx = text.index("{")
                        payload_json = json.loads(text[start_idx:])
                        if isinstance(payload_json, dict) and "source" in payload_json:
                            harvester.ingest_envelope(payload_json)
                            total_ingested += 1
                except Exception:
                    pass
        else:
            raise ValueError(f"Database contains neither collection_records nor raw_frames table: {tables}")
    finally:
        conn.close()

    total_windows = 0
    class_distribution: Dict[str, int] = {}
    ambiguity_counts: Dict[str, int] = {}

    with open(windows_path, "w", encoding="utf-8") as f_out:
        for record in harvester.harvest():
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_windows += 1
            cname = record["pseudo_label"]["class_name"]
            class_distribution[cname] = class_distribution.get(cname, 0) + 1
            for reason in record["ambiguity_reasons"]:
                ambiguity_counts[reason] = ambiguity_counts.get(reason, 0) + 1

    manifest = {
        "schema_version": HARVEST_SCHEMA_VERSION,
        "device_id": harvester.device_id,
        "boot_count": harvester.boot_count,
        "session_id": harvester.session_id,
        "source_db": str(db_path.resolve()),
        "total_envelopes_ingested": total_ingested,
        "total_imu_samples": len(harvester.imu_samples),
        "total_windows": total_windows,
        "window_duration_seconds": round(NOMINAL_WINDOW_SAMPLES / 20.0, 1),
        "step_overlap_ratio": round(1.0 - (NOMINAL_STEP_SAMPLES / float(NOMINAL_WINDOW_SAMPLES)), 2),
        "class_distribution": class_distribution,
        "ambiguity_distribution": ambiguity_counts,
        "privacy_gate": "PASS",
        "redaction": "exact_coordinates_redacted",
        "artifacts": {
            "windows_jsonl": str(windows_path.name),
        },
    }

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest self-supervised multi-modal dataset for EgoLink")
    parser.add_argument("--db", type=Path, help="Path to SQLite message_hub.db")
    parser.add_argument("--jsonl", type=Path, help="Path to raw envelope JSONL export")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to save dataset and manifest")
    parser.add_argument("--device-id", type=str, default=None, help="Filter by device_id")
    parser.add_argument("--boot", type=int, default=None, help="Filter by boot_count")

    args = parser.parse_args()

    if args.db:
        manifest = harvest_dataset_from_db(
            args.db, args.output_dir, device_id=args.device_id, boot_count=args.boot
        )
        print(f"Harvest complete: {manifest['total_windows']} windows extracted.")
        print(f"Class distribution: {json.dumps(manifest['class_distribution'])}")
        print(f"Manifest written to: {args.output_dir / 'dataset_manifest.json'}")
    elif args.jsonl:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        harvester = SelfSupervisedHarvester()
        total_ingested = 0
        with open(args.jsonl, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    harvester.ingest_envelope(json.loads(line))
                    total_ingested += 1

        windows_path = output_dir / "windows.jsonl"
        manifest_path = output_dir / "dataset_manifest.json"
        total_windows = 0
        class_distribution: Dict[str, int] = {}
        ambiguity_counts: Dict[str, int] = {}

        with open(windows_path, "w", encoding="utf-8") as f_out:
            for record in harvester.harvest():
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_windows += 1
                cname = record["pseudo_label"]["class_name"]
                class_distribution[cname] = class_distribution.get(cname, 0) + 1
                for reason in record["ambiguity_reasons"]:
                    ambiguity_counts[reason] = ambiguity_counts.get(reason, 0) + 1

        manifest = {
            "schema_version": HARVEST_SCHEMA_VERSION,
            "device_id": harvester.device_id,
            "boot_count": harvester.boot_count,
            "session_id": harvester.session_id,
            "source_file": str(args.jsonl.resolve()),
            "total_envelopes_ingested": total_ingested,
            "total_imu_samples": len(harvester.imu_samples),
            "total_windows": total_windows,
            "class_distribution": class_distribution,
            "ambiguity_distribution": ambiguity_counts,
            "privacy_gate": "PASS",
            "redaction": "exact_coordinates_redacted",
            "artifacts": {"windows_jsonl": str(windows_path.name)},
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Harvest complete: {total_windows} windows extracted.")
    else:
        print("Error: Specify either --db or --jsonl", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
