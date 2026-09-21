"""Unit and integration tests for Ego-State Store ingestion, queries, and HTTP APIs."""
from __future__ import annotations

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from server import message_hub
from server.collection_store import CONTENT_TYPE
from server.guardian_device_authorization import GuardianDeviceAuthorizer, token_sha256


class EgoStateStoreAndApiTests(unittest.TestCase):
    UPLOAD_TOKEN = "test-device-token-ego-secret"
    GUARDIAN_TOKEN = "test-guardian-token-ego-secret"

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmp_dir.name) / "hub.db"
        cls.store = message_hub.MessageHubStore(cls.db_path)
        guardian = GuardianDeviceAuthorizer({
            "contract_version": "egolink.guardian_device_bindings.v0.1",
            "bindings": [{
                "guardian_id": "test-guardian",
                "token_sha256": token_sha256(cls.GUARDIAN_TOKEN),
                "device_ids": [
                    "ego-link-empty",
                    "ego-link-no-ego",
                    "ego-link-with-ego",
                ],
            }]
        })
        handler_cls = message_hub.make_handler(cls.store, token=cls.UPLOAD_TOKEN, guardian_authorizer=guardian)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.tmp_dir.cleanup()

    def _get(self, path: str, token: str | None = None) -> tuple[int, dict[str, str], dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            raw = resp.read()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return status, resp_headers, body
        finally:
            conn.close()

    def _ingest_envelope(self, env: dict) -> dict:
        dev_id = env["device_id"]
        raw = message_hub.build_raw_frame(
            "event",
            env["observation_id"],
            json.dumps(env, separators=(",", ":")).encode("utf-8"),
            seq=env["sequence_id"],
            content_type=CONTENT_TYPE,
        )
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(
                "POST",
                f"/api/v1/devices/{dev_id}/raw-ingest",
                body=raw,
                headers={
                    "Authorization": f"Bearer {self.UPLOAD_TOKEN}",
                    "X-EgoLink-Transport": "lte",
                    "Content-Type": "application/octet-stream",
                },
            )
            resp = conn.getresponse()
            raw_resp = resp.read()
            self.assertEqual(resp.status, 200, raw_resp)
            return json.loads(raw_resp.decode("utf-8"))
        finally:
            conn.close()

    def _make_device_envelope(self, *, device_id: str, seq: int, boot: int = 1, ego_state: dict | None = None) -> dict:
        payload = {
            "uptime_ms": 10000 + seq * 1000,
            "reset_reason": "power_on",
            "queue_bytes": 0,
        }
        if ego_state is not None:
            payload["ego_state"] = ego_state
        return {
            "contract_version": "egolink.collection.v1",
            "observation_id": f"obs-{device_id}-{boot}-{seq}",
            "device_id": device_id,
            "source": "device",
            "stream_id": "device_health",
            "sequence_id": seq,
            "boot_count": boot,
            "monotonic_clock_domain_id": f"boot-domain-{boot}",
            "timestamp_monotonic_ns": 1000000000 + seq * 1000000000,
            "timestamp_utc": f"2026-09-20T10:00:0{seq}Z",
            "timestamp_source": "cellular_network",
            "timestamp_quality": "synchronized",
            "fw_version": "0.1.0-ego-test",
            "config_id": "cfg-test-01",
            "session_id": "sess-ego-01",
            "status": "ok",
            "missing_reason": None,
            "payload": payload,
        }

    def test_initial_state_empty(self) -> None:
        device_id = "ego-link-empty"
        latest = self.store.collection.latest_ego_state(device_id)
        self.assertIsNone(latest)
        timeline = self.store.collection.ego_state_timeline(device_id)
        self.assertEqual(timeline, [])

        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/latest", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIsNone(body["ego_state"])

    def test_ingest_device_without_ego_state_succeeds(self) -> None:
        device_id = "ego-link-no-ego"
        env = self._make_device_envelope(device_id=device_id, seq=1, ego_state=None)
        res = self._ingest_envelope(env)
        self.assertEqual(res["delivery_ack"]["status"], "accepted")
        self.assertIsNone(self.store.collection.latest_ego_state(device_id))

    def test_ingest_device_with_ego_state_and_queries(self) -> None:
        device_id = "ego-link-with-ego"
        ego_payload = {
            "ready": True,
            "spatial_mobility": "walking",
            "posture_anomaly": "normal",
            "device_wear_state": "worn",
            "confidence": 0.92,
            "window_duration_ms": 2000,
            "primary_evidence_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "is_mock": False,
            "reason_codes": ["R_RHYTHMIC_CADENCE_DETECTED", "R_GROUND_SPEED_CONCORDANT"],
            "evidence_summary": {
                "imu_rms_accel_mg": 285.4,
                "imu_peak_accel_mg": 1420.0,
                "gyro_variance_dps2": 18.5,
                "gnss_ground_speed_mps": 1.25,
                "network_type": "lte",
                "battery_soc_percent": 95.5,
            },
        }
        env = self._make_device_envelope(device_id=device_id, seq=2, ego_state=ego_payload)
        res = self._ingest_envelope(env)
        self.assertEqual(res["delivery_ack"]["status"], "accepted")

        # 1. Query store.collection.latest_ego_state
        latest = self.store.collection.latest_ego_state(device_id)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["spatial_mobility"], "walking")
        self.assertEqual(latest["posture_anomaly"], "normal")
        self.assertEqual(latest["device_wear_state"], "worn")
        self.assertAlmostEqual(latest["confidence"], 0.92, places=2)
        self.assertEqual(latest["window_duration_ms"], 2000)
        self.assertEqual(latest["primary_evidence_digest"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        self.assertFalse(latest["is_mock"])
        self.assertEqual(latest["reason_codes"], ["R_RHYTHMIC_CADENCE_DETECTED", "R_GROUND_SPEED_CONCORDANT"])
        self.assertEqual(latest["evidence_summary"]["imu_rms_accel_mg"], 285.4)
        self.assertTrue(latest["privacy_boundary"]["local_priority"])

        # 2. Check summary contains latest_ego_state
        summary = self.store.collection.summary(device_id)
        self.assertIn("latest_ego_state", summary)
        self.assertEqual(summary["latest_ego_state"]["spatial_mobility"], "walking")

        # 3. HTTP GET /api/v1/devices/<id>/ego-state/latest
        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/latest", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["ego_state"]["spatial_mobility"], "walking")
        self.assertEqual(body["ego_state"]["confidence"], 0.92)

        # 4. HTTP GET /api/v1/devices/<id>/ego-state/timeline
        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/timeline?limit=10", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["timeline"]), 1)
        self.assertEqual(body["timeline"][0]["observation_id"], f"obs-{device_id}-1-2")

        # 5. Ingest subsequent frame with fall alert
        fall_payload = {
            "ready": True,
            "spatial_mobility": "stationary",
            "posture_anomaly": "fall_suspected",
            "device_wear_state": "worn",
            "confidence": 0.88,
            "window_duration_ms": 2000,
            "primary_evidence_digest": "aaaa1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
            "is_mock": False,
            "reason_codes": ["R_PEAK_IMPACT_EXCEEDED", "R_POST_IMPACT_IMMOBILITY"],
            "evidence_summary": {
                "imu_rms_accel_mg": 98.0,
                "imu_peak_accel_mg": 3820.0,
                "gyro_variance_dps2": 2.1,
                "gnss_ground_speed_mps": 0.0,
                "network_type": "lte",
                "battery_soc_percent": 94.8,
            },
        }
        env2 = self._make_device_envelope(device_id=device_id, seq=3, ego_state=fall_payload)
        self._ingest_envelope(env2)

        # Verify latest updated
        latest2 = self.store.collection.latest_ego_state(device_id)
        self.assertEqual(latest2["spatial_mobility"], "stationary")
        self.assertEqual(latest2["posture_anomaly"], "fall_suspected")

        # Verify timeline has 2 items in reverse chronological order
        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/timeline", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["timeline"][0]["posture_anomaly"], "fall_suspected")
        self.assertEqual(body["timeline"][1]["posture_anomaly"], "normal")

        # 6. Legacy collection aliases
        status, _, body = self._get(f"/api/v1/devices/{device_id}/collection/ego-state/latest", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["ego_state"]["posture_anomaly"], "fall_suspected")

        status, _, body = self._get(f"/api/v1/devices/{device_id}/collection/ego-state", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["ego_state"]["posture_anomaly"], "fall_suspected")


if __name__ == "__main__":
    unittest.main()
