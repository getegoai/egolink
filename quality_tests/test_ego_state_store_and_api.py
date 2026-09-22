"""Unit and integration tests for Ego-State Store ingestion, queries, and HTTP APIs."""
from __future__ import annotations

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from server import message_hub
from server.collection_store import CONTENT_TYPE, EGO_ENUMS, _ego_state_projection
from server.guardian_device_authorization import GuardianDeviceAuthorizer, token_sha256

CONTRACTS = Path(__file__).resolve().parents[1] / "shared" / "contracts"
STATE_SCHEMA = json.loads((CONTRACTS / "ego_state_estimation_v0.schema.json").read_text("utf-8"))
VIEW_SCHEMA = json.loads((CONTRACTS / "ego_state_view_v0.schema.json").read_text("utf-8"))
REGISTRY = Registry().with_resource(STATE_SCHEMA["$id"], Resource.from_contents(STATE_SCHEMA))
VIEW_VALIDATOR = Draft202012Validator(VIEW_SCHEMA, registry=REGISTRY, format_checker=FormatChecker())
STATE_VALIDATOR = Draft202012Validator(STATE_SCHEMA, format_checker=FormatChecker())


def valid_payload() -> dict:
    return {
        "ready": True, "spatial_mobility": "pedestrian_walking",
        "posture_anomaly": "normal", "device_wear_state": "wearable_or_bag",
        "confidence": 0.83, "window_duration_ms": 2000,
        "primary_evidence_digest": "a" * 64, "is_mock": False,
        "reason_codes": ["imu_motion", "gnss_motion"],
        "evidence_summary": {"motion_rms_m_s2": 2.3, "imu_sample_count": 40},
    }


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
                    "ego-link-canonical",
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
            "timestamp_utc": None,
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
            "spatial_mobility": "pedestrian_walking",
            "posture_anomaly": "normal",
            "device_wear_state": "wearable_or_bag",
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
        VIEW_VALIDATOR.validate(latest)
        self.assertEqual(latest["state"]["spatial_mobility"], "pedestrian_walking")
        self.assertEqual(latest["state"]["posture_anomaly"], "normal")
        self.assertEqual(latest["state"]["device_wear_state"], "wearable_or_bag")
        self.assertAlmostEqual(latest["state"]["confidence"], 0.92, places=2)
        self.assertEqual(latest["state"]["window_duration_ms"], 2000)
        self.assertEqual(latest["state"]["primary_evidence_digest"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        self.assertFalse(latest["state"]["is_mock"])
        self.assertEqual(latest["state"]["reason_codes"], ["R_RHYTHMIC_CADENCE_DETECTED", "R_GROUND_SPEED_CONCORDANT"])
        self.assertEqual(latest["evidence_summary"]["imu_rms_accel_mg"], 285.4)
        self.assertFalse(latest["storage"]["user_private_endpoint_verified"])
        self.assertFalse(latest["storage"]["automatic_expiry"])
        self.assertFalse(latest["storage"]["encrypted_at_rest"])
        self.assertEqual(latest["provenance"]["identity_source"], "legacy_derived_from_collection_envelope")

        # 2. Check summary contains latest_ego_state
        summary = self.store.collection.summary(device_id)
        self.assertIn("latest_ego_state", summary)
        self.assertEqual(summary["latest_ego_state"]["state"]["spatial_mobility"], "pedestrian_walking")

        # 3. HTTP GET /api/v1/devices/<id>/ego-state/latest
        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/latest", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["ego_state"]["state"]["spatial_mobility"], "pedestrian_walking")
        self.assertEqual(body["ego_state"]["state"]["confidence"], 0.92)
        VIEW_VALIDATOR.validate(body["ego_state"])

        # 4. HTTP GET /api/v1/devices/<id>/ego-state/timeline
        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/timeline?limit=10", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["timeline"]), 1)
        VIEW_VALIDATOR.validate(body["timeline"][0])
        self.assertEqual(body["timeline"][0]["provenance"]["observation_id"], f"obs-{device_id}-1-2")

        # 5. Ingest subsequent frame with fall alert
        fall_payload = {
            "ready": True,
            "spatial_mobility": "stationary",
            "posture_anomaly": "suspected_fall",
            "device_wear_state": "wearable_or_bag",
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
        self.assertEqual(latest2["state"]["spatial_mobility"], "stationary")
        self.assertEqual(latest2["state"]["posture_anomaly"], "suspected_fall")

        # Verify timeline has 2 items in reverse chronological order
        status, _, body = self._get(f"/api/v1/devices/{device_id}/ego-state/timeline", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["timeline"][0]["state"]["posture_anomaly"], "suspected_fall")
        self.assertEqual(body["timeline"][1]["state"]["posture_anomaly"], "normal")

        # 6. Legacy collection aliases
        status, _, body = self._get(f"/api/v1/devices/{device_id}/collection/ego-state/latest", token=self.GUARDIAN_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["ego_state"]["state"]["posture_anomaly"], "suspected_fall")

    def test_new_canonical_view_preserves_source_time_and_schema(self) -> None:
        env = self._make_device_envelope(device_id="ego-link-canonical", seq=1, ego_state=valid_payload())
        env["payload"]["ego_state"].update({
            "contract_version": "egolink.ego_state_estimation.v0.1",
            "estimation_id": "est-1", "device_id": env["device_id"], "boot_count": env["boot_count"],
            "timestamp_monotonic_ns": env["timestamp_monotonic_ns"] - 1000, "timestamp_utc": None,
        })
        self._ingest_envelope(env)
        for suffix in ("ego-state/latest", "ego-state", "collection/ego-state/latest", "collection/ego-state"):
            status, headers, body = self._get(f'/api/v1/devices/{env["device_id"]}/{suffix}', token=self.GUARDIAN_TOKEN)
            self.assertEqual(status, 200)
            self.assertEqual(headers["cache-control"], "no-store")
            view = body["ego_state"]
            VIEW_VALIDATOR.validate(view)
            self.assertEqual(view["provenance"]["identity_source"], "device")
            self.assertEqual(view["provenance"]["digest_verification"], "not_performed")
            self.assertEqual(view["state"]["estimation_id"], "est-1")
            self.assertEqual(view["state"]["timestamp_monotonic_ns"], env["timestamp_monotonic_ns"] - 1000)
            self.assertIsNone(view["state"]["timestamp_utc"])
            self.assertIsNotNone(view["receipt"]["server_received_at"])
            self.assertNotIn("privacy_boundary", view)
        for suffix in ("ego-state/timeline", "collection/ego-state/timeline"):
            status, _, body = self._get(f'/api/v1/devices/{env["device_id"]}/{suffix}?limit=1', token=self.GUARDIAN_TOKEN)
            self.assertEqual(status, 200)
            VIEW_VALIDATOR.validate(body["timeline"][0])

    def test_new_invalid_optional_states_do_not_poison_raw_ack_or_valid_latest(self) -> None:
        device = "ego-link-invalid"
        env = self._make_device_envelope(device_id=device, seq=1, ego_state=valid_payload())
        self._ingest_envelope(env)
        accepted = self.store.collection.latest_ego_state(device)
        self.assertEqual(accepted["state"]["estimation_id"], env["observation_id"])
        self.assertIsNone(accepted["state"]["timestamp_utc"])
        patches = [
            {"spatial_mobility": "walking"}, {"posture_anomaly": "fall_suspected"},
            {"device_wear_state": "worn"}, {"confidence": 1.1}, {"confidence": "0.9"},
            {"confidence": True}, {"window_duration_ms": 99}, {"window_duration_ms": "2000"},
            {"is_mock": 0}, {"primary_evidence_digest": "bad"}, {"reason_codes": []},
            {"reason_codes": ["same", "same"]}, {"evidence_summary": []},
            {"contract_version": "egolink.ego_state_estimation.v0.1"}, {"ready": "true"},
            {"confidence": 10 ** 400}, {"reason_codes": [{}]}, {"unexpected": "extra"},
        ]
        for seq, patch in enumerate(patches, start=2):
            with self.subTest(patch=patch):
                bad = self._make_device_envelope(device_id=device, seq=seq, ego_state=dict(valid_payload(), **patch))
                result = self._ingest_envelope(bad)
                self.assertEqual(result["delivery_ack"]["status"], "accepted")
                self.assertEqual(self.store.collection.latest_ego_state(device), accepted)
                source = self.store.collection.summary(device)["sources"][0]
                self.assertEqual(source["latest"]["preview"]["ego_state_projection"]["status"], "invalid")
        self.assertEqual(len(self.store.collection.ego_state_timeline(device)), 1)
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_records WHERE device_id=?", (device,)).fetchone()[0], len(patches) + 1)
        missing = self._make_device_envelope(device_id=device, seq=100, ego_state={"ready": True})
        self._ingest_envelope(missing)
        unavailable = self._make_device_envelope(device_id=device, seq=101, ego_state={"ready": False})
        self._ingest_envelope(unavailable)
        self.assertEqual(self.store.collection.latest_ego_state(device), accepted)
        self.assertEqual(self.store.collection.summary(device)["sources"][0]["latest"]["preview"]["ego_state_projection"]["status"], "unavailable")

    def test_new_historical_invalid_index_row_does_not_mask_valid_result_limit(self) -> None:
        device = "ego-link-history"
        self._ingest_envelope(self._make_device_envelope(device_id=device, seq=1, ego_state=valid_payload()))
        bad = self._make_device_envelope(device_id=device, seq=20, ego_state=dict(valid_payload(), spatial_mobility="walking"))
        self._ingest_envelope(bad)
        with self.store.connection() as db:
            old = dict(db.execute("SELECT * FROM collection_ego_states WHERE device_id=?", (device,)).fetchone())
            record_id = db.execute("SELECT id FROM collection_records WHERE device_id=? AND observation_id=?", (device, bad["observation_id"])).fetchone()[0]
            old.pop("id")
            old.update(observation_id=bad["observation_id"], record_id=record_id, event_monotonic_ns=bad["timestamp_monotonic_ns"], sequence_id=20, spatial_mobility="walking", ego_state_json=json.dumps(bad["payload"]["ego_state"]))
            db.execute(f'INSERT INTO collection_ego_states ({",".join(old)}) VALUES ({",".join("?" for _ in old)})', tuple(old.values()))
        views = self.store.collection.ego_state_timeline(device, limit=1)
        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]["provenance"]["sequence_id"], 1)
        self.assertEqual(self.store.collection.latest_ego_state(device), views[0])
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_ego_states WHERE device_id=?", (device,)).fetchone()[0], 2)

    def test_split_health_does_not_hide_state_packet_diagnostics(self) -> None:
        device = "ego-link-split"
        self.assertIsNone(self.store.collection.summary(device)["latest_ego_state_projection"])
        good = self._make_device_envelope(device_id=device, boot=2, seq=1, ego_state=valid_payload())
        self._ingest_envelope(good)
        self._ingest_envelope(self._make_device_envelope(device_id=device, boot=2, seq=2))
        summary = self.store.collection.summary(device)
        self.assertEqual(summary["sources"][0]["latest"]["preview"]["ego_state_projection"]["status"], "absent")
        self.assertEqual(summary["latest_ego_state_projection"]["status"], "valid")
        self.assertEqual(summary["latest_ego_state_projection"]["observation_id"], good["observation_id"])
        bad = self._make_device_envelope(device_id=device, boot=2, seq=3,
                                         ego_state=dict(valid_payload(), posture_anomaly="legacy_bad_value"))
        self._ingest_envelope(bad)
        self._ingest_envelope(self._make_device_envelope(device_id=device, boot=2, seq=4))
        # A delayed old boot cannot replace the newer packet's diagnostic.
        self._ingest_envelope(self._make_device_envelope(device_id=device, boot=1, seq=100,
                                                        ego_state={"ready": False}))
        summary = self.store.collection.summary(device)
        self.assertEqual(summary["latest_ego_state_projection"]["status"], "invalid")
        self.assertEqual(summary["latest_ego_state_projection"]["observation_id"], bad["observation_id"])
        self.assertEqual(summary["latest_ego_state"]["provenance"]["observation_id"], good["observation_id"])
        self._ingest_envelope(self._make_device_envelope(device_id=device, boot=2, seq=5,
                                                        ego_state={"ready": False}))
        self._ingest_envelope(self._make_device_envelope(device_id=device, boot=2, seq=6))
        self.assertEqual(self.store.collection.summary(device)["latest_ego_state_projection"]["status"], "unavailable")

    def test_new_boot_order_duplicate_and_conflict_remain_truthful(self) -> None:
        device = "ego-link-order"
        for boot, seq in ((2, 3), (1, 100), (2, 1)):
            self._ingest_envelope(self._make_device_envelope(device_id=device, seq=seq, boot=boot, ego_state=valid_payload()))
        latest = self._make_device_envelope(device_id=device, seq=3, boot=2, ego_state=valid_payload())
        self.assertEqual(self._ingest_envelope(latest)["result"], "duplicate")
        timeline = self.store.collection.ego_state_timeline(device)
        self.assertEqual([(v["state"]["boot_count"], v["provenance"]["sequence_id"]) for v in timeline], [(2, 3), (2, 1), (1, 100)])
        for view in timeline:
            VIEW_VALIDATOR.validate(view)
        latest["payload"]["ego_state"]["confidence"] = 0.4
        raw = message_hub.build_raw_frame("event", latest["observation_id"], json.dumps(latest).encode(), seq=3, content_type=CONTENT_TYPE)
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("POST", f"/api/v1/devices/{device}/raw-ingest", body=raw, headers={"Authorization": f"Bearer {self.UPLOAD_TOKEN}", "X-EgoLink-Transport": "lte"})
            response = conn.getresponse()
            self.assertEqual(response.status, 409, response.read())
        finally:
            conn.close()
        self.assertEqual(self.store.collection.latest_ego_state(device)["state"]["confidence"], 0.83)

    def test_new_legacy_index_time_cannot_override_canonical_source_order(self) -> None:
        device = "ego-link-old-index-time"
        for seq, event_time in ((5, 100), (3, 500), (1, 400)):
            env = self._make_device_envelope(device_id=device, seq=seq, ego_state=valid_payload())
            env["payload"]["ego_state"].update({
                "contract_version": "egolink.ego_state_estimation.v0.1", "estimation_id": f"est-{seq}",
                "device_id": device, "boot_count": 1,
                "timestamp_monotonic_ns": event_time, "timestamp_utc": None,
            })
            self._ingest_envelope(env)
            # Older indexing code stored the later envelope timestamp, while
            # the immutable state retained the actual earlier evaluation time.
            with self.store.connection() as db:
                db.execute("UPDATE collection_ego_states SET event_monotonic_ns=? WHERE device_id=? AND observation_id=?", (env["timestamp_monotonic_ns"], device, env["observation_id"]))
        self.assertEqual(self.store.collection.latest_ego_state(device)["state"]["timestamp_monotonic_ns"], 500)
        self.assertEqual([view["state"]["timestamp_monotonic_ns"] for view in self.store.collection.ego_state_timeline(device, limit=2)], [500, 400])
        self.assertEqual([view["state"]["timestamp_monotonic_ns"] for view in self.store.collection.ego_state_timeline(device)], [500, 400, 100])

    def test_new_guardian_binding_protects_all_ego_routes(self) -> None:
        for suffix in ("ego-state", "ego-state/latest", "ego-state/timeline", "collection/ego-state", "collection/ego-state/latest", "collection/ego-state/timeline"):
            for device, token in (("ego-link-with-ego", None), ("ego-link-with-ego", self.UPLOAD_TOKEN), ("ego-link-unbound", self.GUARDIAN_TOKEN)):
                with self.subTest(device=device, suffix=suffix, token=token):
                    status, _, body = self._get(f"/api/v1/devices/{device}/{suffix}", token=token)
                    self.assertIn(status, (401, 403))
                    self.assertNotIn("ego_state", body)

    def test_new_runtime_adapter_oracle_and_identity_failures(self) -> None:
        env = self._make_device_envelope(device_id="ego-link-oracle", seq=1, ego_state=valid_payload())
        for field, values in EGO_ENUMS.items():
            for value in values:
                env["payload"]["ego_state"] = dict(valid_payload(), **{field: value}, is_mock=True)
                state, diagnostic = _ego_state_projection(env)
                self.assertEqual(diagnostic["status"], "valid")
                STATE_VALIDATOR.validate(state)
        identity = {"contract_version": "egolink.ego_state_estimation.v0.1", "estimation_id": "est-1", "device_id": env["device_id"], "boot_count": 1, "timestamp_monotonic_ns": env["timestamp_monotonic_ns"], "timestamp_utc": None}
        for patch in ({"device_id": "other-device"}, {"boot_count": 2}, {"boot_count": True}, {"estimation_id": ""}, {"timestamp_monotonic_ns": env["timestamp_monotonic_ns"] + 1}, {"timestamp_utc": "not-a-time"}, {"timestamp_utc": "2026-W01-1T00:00:00Z"}, {"confidence": float("nan")}, {"confidence": float("inf")}):
            with self.subTest(patch=patch):
                env["payload"]["ego_state"] = {**valid_payload(), **identity, **patch}
                state, diagnostic = _ego_state_projection(env)
                self.assertIsNone(state)
                self.assertEqual(diagnostic["status"], "invalid")
        env["payload"]["ego_state"] = {**valid_payload(), **identity, "is_mock": True}
        env["payload"]["is_mock"] = False
        state, diagnostic = _ego_state_projection(env)
        self.assertEqual(diagnostic["status"], "valid")
        self.assertTrue(state["is_mock"])
        env["payload"]["ego_state"]["is_mock"] = False
        env["payload"]["is_mock"] = True
        state, diagnostic = _ego_state_projection(env)
        self.assertIsNone(state)
        self.assertEqual(diagnostic["reason_code"], "ego_state_mock_lineage_mismatch")

if __name__ == "__main__":
    unittest.main()
