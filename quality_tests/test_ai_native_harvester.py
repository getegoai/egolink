from __future__ import annotations

import base64
import json
import math
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest

from scripts.harvest_self_supervised_dataset import (
    decode_imu_chunk,
    compute_window_features,
    find_nearest_observation,
    self_supervised_label,
    SelfSupervisedHarvester,
    harvest_dataset_from_db,
    HARVEST_SCHEMA_VERSION,
    WINDOW_RECORD_SCHEMA_VERSION,
)


class TestAiNativeHarvester(unittest.TestCase):
    def test_decode_imu_chunk(self):
        # 2 samples: 32 bytes
        # Sample 0: offset_us = 0, ax = 1000 mg (~8192 raw), ay = 0, az = 0, gx = 0, gy = 0, gz = 0
        raw_divisor = 32768
        accel_scale = 4000  # mg
        ax_raw = int(1000.0 * raw_divisor / accel_scale)  # 8192
        sample0 = struct.pack("<I6h", 0, ax_raw, 0, 0, 0, 0, 0)

        # Sample 1: offset_us = 50000 (50ms), az = 1000 mg, gz = 50000 mdps (50 dps)
        gyro_scale = 512000
        gz_raw = int(50000.0 * raw_divisor / gyro_scale)
        sample1 = struct.pack("<I6h", 50000, 0, 0, ax_raw, 0, 0, gz_raw)

        binary_data = sample0 + sample1
        b64 = base64.b64encode(binary_data).decode("ascii")

        payload = {
            "encoding": "offset_us+six_i16le+base64-v1",
            "samples_b64": b64,
            "sample_count": 2,
            "sample_record_bytes": 16,
            "accel_full_scale_mg": accel_scale,
            "gyro_full_scale_mdps": gyro_scale,
            "raw_divisor": raw_divisor,
        }

        decoded = decode_imu_chunk(payload, base_timestamp_ns=1_000_000_000)
        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded[0]["t_ns"], 1_000_000_000)
        self.assertAlmostEqual(decoded[0]["ax"], 1000.0 * 0.00980665, delta=0.05)
        self.assertAlmostEqual(decoded[0]["ay"], 0.0, delta=0.01)

        self.assertEqual(decoded[1]["t_ns"], 1_000_000_000 + 50_000_000)
        self.assertAlmostEqual(decoded[1]["az"], 1000.0 * 0.00980665, delta=0.05)
        self.assertAlmostEqual(decoded[1]["gz"], 50.0, delta=0.1)

    def test_decode_invalid_length_raises(self):
        payload = {
            "samples_b64": base64.b64encode(b"invalid_length_15b").decode("ascii"),
            "sample_record_bytes": 16,
        }
        with self.assertRaises(ValueError):
            decode_imu_chunk(payload, 0)

    def test_compute_window_features(self):
        # 100 samples of pure static gravity az = 9.80665
        samples = []
        for i in range(100):
            samples.append({
                "t_ns": 1_000_000_000 + i * 50_000_000,
                "ax": 0.0,
                "ay": 0.0,
                "az": 9.80665,
                "gx": 0.0,
                "gy": 0.0,
                "gz": 0.0,
            })
        feats = compute_window_features(samples)
        self.assertEqual(feats["sample_count"], 100)
        self.assertAlmostEqual(feats["duration_ms"], 4950.0, delta=1.0)
        self.assertAlmostEqual(feats["sample_rate_hz"], 20.0, delta=0.5)
        self.assertAlmostEqual(feats["mean_accel_m_s2"], 9.80665, delta=0.01)
        self.assertAlmostEqual(feats["motion_rms_m_s2"], 0.0, delta=0.001)
        self.assertAlmostEqual(feats["peak_accel_m_s2"], 9.80665, delta=0.01)
        self.assertAlmostEqual(feats["gyro_variance_dps2"], 0.0, delta=0.001)
        self.assertEqual(feats["cadence_hz"], 0.0)

    def test_self_supervised_labeling_classes(self):
        # 1. Fall suspected (Shock followed by immobility)
        fall_feats = {
            "motion_rms_m_s2": 0.08,
            "peak_accel_m_s2": 28.5,
            "gyro_variance_dps2": 0.05,
            "cadence_hz": 0.0,
        }
        label, ambig = self_supervised_label(fall_feats, None, None, None, None)
        self.assertEqual(label["class_name"], "fall_suspected")

        # 2. Charging dock
        charging_feats = {
            "motion_rms_m_s2": 0.02,
            "peak_accel_m_s2": 9.81,
            "gyro_variance_dps2": 0.01,
            "cadence_hz": 0.0,
        }
        power_chg = {"charging": True, "battery_mv": 4200}
        label, ambig = self_supervised_label(charging_feats, None, power_chg, None, None)
        self.assertEqual(label["class_name"], "stationary_charging")

        # 3. In-vehicle (GNSS speed >= 6.5 m/s)
        veh_feats = {
            "motion_rms_m_s2": 0.25,
            "peak_accel_m_s2": 11.0,
            "gyro_variance_dps2": 0.5,
            "cadence_hz": 0.0,
        }
        gnss_veh = {"fix": True, "speed_mps": 12.5, "hdop": 1.1}
        label, ambig = self_supervised_label(veh_feats, gnss_veh, None, None, None)
        self.assertEqual(label["class_name"], "in_vehicle")

        # 4. Cycling (GNSS speed 4.5 m/s + moderate RMS)
        bike_feats = {
            "motion_rms_m_s2": 0.55,
            "peak_accel_m_s2": 12.0,
            "gyro_variance_dps2": 1.2,
            "cadence_hz": 1.1,
        }
        gnss_bike = {"fix": True, "speed_mps": 4.5, "hdop": 1.0}
        label, ambig = self_supervised_label(bike_feats, gnss_bike, None, None, None)
        self.assertEqual(label["class_name"], "cycling")

        # 5. Running (High RMS and cadence)
        run_feats = {
            "motion_rms_m_s2": 1.85,
            "peak_accel_m_s2": 18.0,
            "gyro_variance_dps2": 5.0,
            "cadence_hz": 2.8,
        }
        gnss_run = {"fix": True, "speed_mps": 3.0, "hdop": 1.2}
        label, ambig = self_supervised_label(run_feats, gnss_run, None, None, None)
        self.assertEqual(label["class_name"], "running")

        # 6. Walking (Pedestrian cadence and RMS)
        walk_feats = {
            "motion_rms_m_s2": 0.65,
            "peak_accel_m_s2": 13.5,
            "gyro_variance_dps2": 2.0,
            "cadence_hz": 1.8,
        }
        gnss_walk = {"fix": True, "speed_mps": 1.2, "hdop": 1.5}
        label, ambig = self_supervised_label(walk_feats, gnss_walk, None, None, None)
        self.assertEqual(label["class_name"], "walking")

        # 7. Stationary
        stat_feats = {
            "motion_rms_m_s2": 0.04,
            "peak_accel_m_s2": 9.82,
            "gyro_variance_dps2": 0.02,
            "cadence_hz": 0.0,
        }
        gnss_stat = {"fix": True, "speed_mps": 0.05, "hdop": 1.0}
        label, ambig = self_supervised_label(stat_feats, gnss_stat, None, None, None)
        self.assertEqual(label["class_name"], "stationary")

    def test_ambiguity_detection(self):
        # Ambiguity: High motion but 0 m/s GNSS (e.g. treadmill / desk fidget)
        treadmill_feats = {
            "motion_rms_m_s2": 1.2,
            "peak_accel_m_s2": 15.0,
            "gyro_variance_dps2": 3.0,
            "cadence_hz": 2.0,
        }
        gnss_zero = {"fix": True, "speed_mps": 0.05, "hdop": 1.0}
        _, ambig = self_supervised_label(treadmill_feats, gnss_zero, None, None, None)
        self.assertIn("high_motion_zero_velocity", ambig)

        # Ambiguity: Rule disagreement
        ego_rule = {"spatial_mobility": "pedestrian_walking"}
        stat_feats = {
            "motion_rms_m_s2": 0.04,
            "peak_accel_m_s2": 9.82,
            "gyro_variance_dps2": 0.02,
            "cadence_hz": 0.0,
        }
        _, ambig2 = self_supervised_label(stat_feats, None, None, None, ego_rule)
        self.assertTrue(any("rule_disagreement" in a for a in ambig2))

    def test_end_to_end_harvester_stream(self):
        harvester = SelfSupervisedHarvester(window_samples=100, step_samples=50)

        # Synthesize 150 IMU samples (3 chunks of 50 samples)
        # Sample rate: 20Hz (dt = 50ms = 50,000us)
        raw_divisor = 32768
        ax_raw = int(1000.0 * raw_divisor / 4000.0)

        for chunk_idx in range(3):
            samples_binary = bytearray()
            for s_idx in range(50):
                offset_us = s_idx * 50000
                samples_binary.extend(struct.pack("<I6h", offset_us, 0, 0, ax_raw, 0, 0, 0))

            b64 = base64.b64encode(samples_binary).decode("ascii")
            harvester.ingest_envelope({
                "source": "imu",
                "device_id": "test-node-001",
                "boot_count": 211,
                "session_id": "col-b211",
                "timestamp_monotonic_ns": (chunk_idx * 50 * 50_000_000),
                "payload": {
                    "encoding": "offset_us+six_i16le+base64-v1",
                    "samples_b64": b64,
                    "sample_count": 50,
                    "sample_record_bytes": 16,
                    "accel_full_scale_mg": 4000,
                    "gyro_full_scale_mdps": 512000,
                    "raw_divisor": raw_divisor,
                },
            })

        # Add GNSS fix
        harvester.ingest_envelope({
            "source": "gnss",
            "device_id": "test-node-001",
            "boot_count": 211,
            "timestamp_monotonic_ns": 2_500_000_000,
            "payload": {
                "fix": True,
                "speed_mps": 0.02,
                "hdop": 0.8,
                "satellites": 16,
            },
        })

        # Add Power reading
        harvester.ingest_envelope({
            "source": "power",
            "device_id": "test-node-001",
            "boot_count": 211,
            "timestamp_monotonic_ns": 2_500_000_000,
            "payload": {
                "charging": False,
                "battery_millivolt": 4120,
                "fuel_gauge_soc_percent": 88.5,
            },
        })

        windows = list(harvester.harvest())
        # 150 samples with window=100 and step=50 gives exactly 2 windows
        self.assertEqual(len(windows), 2)
        w0 = windows[0]
        self.assertEqual(w0["schema_version"], WINDOW_RECORD_SCHEMA_VERSION)
        self.assertEqual(w0["device_id"], "test-node-001")
        self.assertEqual(w0["boot_count"], 211)
        self.assertEqual(w0["imu_features"]["sample_count"], 100)
        self.assertEqual(w0["tensor_shape"], [100, 6])
        self.assertEqual(len(w0["raw_tensor"]), 100)
        self.assertEqual(len(w0["raw_tensor"][0]), 6)
        self.assertEqual(w0["pseudo_label"]["class_name"], "stationary")
        self.assertTrue(w0["cross_modal_context"]["gnss_fix"])
        self.assertEqual(w0["cross_modal_context"]["battery_mv"], 4120)

    def test_sqlite_db_harvest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "message_hub.db"
            out_dir = Path(tmp_dir) / "harvested_dataset"

            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE collection_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL, observation_id TEXT NOT NULL,
                    raw_frame_id INTEGER NOT NULL, payload_sha256 TEXT NOT NULL,
                    source TEXT NOT NULL, stream_id TEXT NOT NULL,
                    sequence_id INTEGER NOT NULL, boot_count INTEGER NOT NULL,
                    clock_domain TEXT NOT NULL, event_monotonic_ns INTEGER NOT NULL,
                    event_utc TEXT, session_id TEXT, fw_version TEXT NOT NULL,
                    config_id TEXT NOT NULL, acquisition_status TEXT NOT NULL,
                    parse_status TEXT NOT NULL, sample_count INTEGER NOT NULL,
                    frame_bytes INTEGER NOT NULL, received_at TEXT NOT NULL,
                    persisted_at TEXT NOT NULL, envelope_json TEXT NOT NULL,
                    preview_json TEXT NOT NULL
                );
            """)

            # Insert 100 IMU samples into SQLite
            raw_divisor = 32768
            ax_raw = int(1000.0 * raw_divisor / 4000.0)
            binary_samples = bytearray()
            for i in range(100):
                binary_samples.extend(struct.pack("<I6h", i * 50000, 0, 0, ax_raw, 0, 0, 0))
            b64 = base64.b64encode(binary_samples).decode("ascii")

            env = {
                "source": "imu",
                "device_id": "connectivity-node-001",
                "boot_count": 211,
                "session_id": "col-b211",
                "sequence_id": 1,
                "timestamp_monotonic_ns": 1_000_000_000,
                "payload": {
                    "encoding": "offset_us+six_i16le+base64-v1",
                    "samples_b64": b64,
                    "sample_count": 100,
                    "sample_record_bytes": 16,
                    "accel_full_scale_mg": 4000,
                    "gyro_full_scale_mdps": 512000,
                    "raw_divisor": raw_divisor,
                },
            }
            conn.execute(
                """
                INSERT INTO collection_records (
                    device_id, observation_id, raw_frame_id, payload_sha256,
                    source, stream_id, sequence_id, boot_count, clock_domain,
                    event_monotonic_ns, fw_version, config_id, acquisition_status,
                    parse_status, sample_count, frame_bytes, received_at, persisted_at,
                    envelope_json, preview_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "connectivity-node-001", "obs-1", 1, "sha",
                    "imu", "imu-stream", 1, 211, "clk",
                    1_000_000_000, "fw-v1", "cfg", "observed",
                    "parsed", 100, len(b64), "2026-09-23T00:00:00Z", "2026-09-23T00:00:00Z",
                    json.dumps(env), "{}"
                ),
            )
            conn.commit()
            conn.close()

            manifest = harvest_dataset_from_db(db_path, out_dir, device_id="connectivity-node-001", boot_count=211)
            self.assertEqual(manifest["schema_version"], HARVEST_SCHEMA_VERSION)
            self.assertEqual(manifest["total_windows"], 1)
            self.assertEqual(manifest["privacy_gate"], "PASS")

            # Check that files were created
            manifest_file = out_dir / "dataset_manifest.json"
            windows_file = out_dir / "windows.jsonl"
            self.assertTrue(manifest_file.is_file())
            self.assertTrue(windows_file.is_file())

            windows_lines = windows_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(windows_lines), 1)
            parsed_win = json.loads(windows_lines[0])
            self.assertEqual(parsed_win["pseudo_label"]["class_name"], "stationary")
            # Verify coordinates privacy (no lat or lon keys present)
            self.assertNotIn("latitude", parsed_win["cross_modal_context"])
            self.assertNotIn("longitude", parsed_win["cross_modal_context"])


if __name__ == "__main__":
    unittest.main()
