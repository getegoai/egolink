from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
import unittest
from urllib import error, parse, request

from jsonschema import Draft202012Validator

from server import message_hub
from server.collection_store import CollectionError, CONTENT_TYPE
from server.guardian_device_authorization import GuardianDeviceAuthorizer, token_sha256


DEVICE = "collection-test-001"
PROJECT_TOKEN = "test-project-token-not-a-real-credential"
UPLOAD_TOKEN = "test-device-token-not-a-real-credential"
FIRMWARE_ELF_SHA256 = "ab" * 32


def envelope(sequence=1, source="gnss", **changes):
    value = {
        "contract_version": "egolink.collection.v1", "observation_id": f"test-b1-{sequence}",
        "device_id": DEVICE, "source": source, "stream_id": source + "-test", "sequence_id": sequence,
        "boot_count": 1, "monotonic_clock_domain_id": "test-boot-1", "timestamp_monotonic_ns": sequence * 1_000_000_000,
        "timestamp_utc": None, "timestamp_source": "unavailable", "timestamp_quality": "unknown",
        "fw_version": "test-collector", "config_id": "test-config-v1", "session_id": "test-session",
        "status": "no_fix", "payload": {"at": [{"command": "AT+CGNSSINFO", "response": "+CGNSSINFO: ,,,,,,,,\r\nOK\r\n", "outcome": "no_fix", "elapsed_ms": 13}], "parsed": None},
        "missing_reason": "indoor_no_fix",
    }
    value.update(changes)
    return value


def wifi_scan_payload(**changes):
    value = {
        "channel_summary": [
            {"channel": 1, "ap_count": 2, "strongest_rssi": -41},
            {"channel": 11, "ap_count": 1, "strongest_rssi": -67},
        ],
        "scan_result": 0,
        "total_seen": 3,
        "truncated": False,
        "sampled_ap_count": 3,
        "identifiers_retained": False,
        "privacy_reason": "raw_wifi_identifiers_disabled",
        "connected": True,
        "disconnect_reason": 0,
    }
    value.update(changes)
    return value


def frame(value):
    return message_hub.build_raw_frame("event", value["observation_id"], json.dumps(value, separators=(",", ":")).encode(), seq=value["sequence_id"], content_type=CONTENT_TYPE)


def raw_record(raw, device=DEVICE):
    return message_hub.parse_raw_frame_record(message_hub.initial_raw_frame_record(device, raw, "uplink", message_hub.utc_now()), raw, expected_frame_type="event")


def authorizer():
    return GuardianDeviceAuthorizer({"contract_version": "egolink.guardian_device_bindings.v0.1", "bindings": [{"guardian_id": "test-project", "token_sha256": token_sha256(PROJECT_TOKEN), "device_ids": [DEVICE]}]})


@contextmanager
def running_hub(store, *, token=UPLOAD_TOKEN, binding=True):
    handler = message_hub.make_handler(store, token=token, guardian_authorizer=authorizer() if binding else None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def http(base, path, *, body=None, token=None, transport=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if transport is not None:
        headers["X-EgoLink-Transport"] = transport
    req = request.Request(base + path, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        response = request.urlopen(req, timeout=5)
    except error.HTTPError as failure:
        response = failure
    with response:
        return response.status, response.read(), dict(response.headers)


class CollectionIngestTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.store = message_hub.MessageHubStore(Path(self.root.name) / "hub.db")

    def ingest(self, value, transport="wifi"):
        raw = frame(value)
        return self.store.collection.ingest(raw, raw_record(raw), transport=transport)

    def table_counts(self):
        with self.store.connection() as db:
            return tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                         for table in ("raw_frames", "collection_records", "collection_delivery_attempts"))

    def test_collection_is_main_entry_and_engineering_view_remains_available(self):
        with running_hub(self.store) as base:
            root_status, root, headers = http(base, "/")
            collection_status, collection, _ = http(base, "/collection")
            engineering_status, engineering, _ = http(base, "/engineering")
        self.assertEqual((root_status, collection_status, engineering_status), (200, 200, 200))
        self.assertEqual(root, collection)
        self.assertIn(b"/collection.js", root)
        self.assertIn("Content-Security-Policy", headers)
        self.assertNotEqual(engineering, root)
        self.assertIn(b"/collection", engineering)

    def test_no_fix_and_unsynchronized_time_durably_ack_exact_raw_frame(self):
        value, raw = envelope(), frame(envelope())
        with running_hub(self.store) as base:
            status, body, headers = http(base, f"/api/v1/devices/{DEVICE}/raw-ingest", body=raw, token=UPLOAD_TOKEN, transport="wifi")
            self.assertEqual(status, 200, body)
            ack = json.loads(body)["delivery_ack"]
            self.assertEqual(ack["payload_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(ack["event_id"], value["observation_id"])
            self.assertEqual(ack["device_id"], DEVICE)
            self.assertEqual(ack["status"], "accepted")
            self.assertEqual(headers["Cache-Control"], "no-store")
            # The committed raw bytes are readable through another SQLite connection before acknowledgement is used.
            with closing(sqlite3.connect(self.store.db_path)) as db:
                stored = db.execute("SELECT raw_payload_b64 FROM raw_frames").fetchone()[0]
                self.assertEqual(base64.b64decode(stored), raw)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_records").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
            code, output, _ = http(base, f"/api/v1/devices/{DEVICE}/collection/summary", token=PROJECT_TOKEN)
            self.assertEqual(code, 200)
            summary = json.loads(output)
            self.assertEqual(summary["sources"][0]["no_fix"], 1)
            self.assertIsNone(summary["sources"][0]["latest"]["envelope"]["timestamp_utc"])

    def test_wifi_privacy_guard_rejects_top_nested_case_and_raw_ap_variants_before_writes(self):
        prohibited = (
            {"ssid": "private-network-name"},
            {"metadata": {"BsSiD": "00:11:22:33:44:55"}},
            {"samples": [{"MaC": "00:11:22:33:44:55"}]},
            {"RaW_scan": "private-scan-bytes"},
            {"APs": [{"identifier": "opaque-private-id", "rssi": -42}]},
        )
        details = set()
        for sequence, payload in enumerate(prohibited, 20):
            with self.subTest(payload=next(iter(payload))):
                with self.assertRaises(CollectionError) as raised:
                    self.ingest(envelope(sequence, source="wifi", status="observed", payload=payload, missing_reason=None))
                self.assertEqual(raised.exception.code, "collection_privacy_policy_rejected")
                self.assertEqual(raised.exception.status, 422)
                details.add(str(raised.exception))
        self.assertEqual(details, {"Wi-Fi collection payload violates the privacy admission policy"})
        renamed_top_level = envelope(29, source="wifi", status="observed",
                                     payload=wifi_scan_payload(), missing_reason=None)
        renamed_top_level["wifi_bssid"] = "00:11:22:33:44:55"
        with self.assertRaises(CollectionError) as raised:
            self.store.collection.ingest(frame(renamed_top_level), raw_record(frame(renamed_top_level)), transport="wifi")
        self.assertEqual(raised.exception.code, "collection_privacy_policy_rejected")
        self.assertEqual(self.table_counts(), (0, 0, 0))

    def test_wifi_privacy_http_rejection_has_no_echo_ack_rows_or_delivery_attempt(self):
        private_value = "operator-private-network"
        value = envelope(30, source="wifi", status="observed",
                         payload={"nested": {"SSID": private_value}}, missing_reason=None)
        with running_hub(self.store) as base:
            code, body, _ = http(base, f"/api/v1/devices/{DEVICE}/raw-ingest",
                                 body=frame(value), token=UPLOAD_TOKEN, transport="wifi")
        response = json.loads(body)
        self.assertEqual(code, 422, body)
        self.assertEqual(response, {
            "ok": False,
            "error": "collection_privacy_policy_rejected",
            "detail": "Wi-Fi collection payload violates the privacy admission policy",
        })
        self.assertNotIn(private_value, body.decode())
        self.assertNotIn("delivery_ack", response)
        self.assertEqual(self.table_counts(), (0, 0, 0))

    def test_wifi_privacy_rejection_precedes_existing_identity_conflict(self):
        accepted = envelope(40, source="wifi", status="connected",
                            payload={"phase": "link_event", "connected": True}, missing_reason=None)
        self.ingest(accepted)
        conflicting_private = {**accepted, "payload": {"BSSID": "00:11:22:33:44:55"}}
        with running_hub(self.store) as base:
            code, body, _ = http(base, f"/api/v1/devices/{DEVICE}/raw-ingest",
                                 body=frame(conflicting_private), token=UPLOAD_TOKEN, transport="lte")
        response = json.loads(body)
        self.assertEqual(code, 422, body)
        self.assertEqual(response["error"], "collection_privacy_policy_rejected")
        self.assertNotIn("delivery_ack", response)
        self.assertEqual(self.table_counts(), (1, 1, 1))

    def test_complete_identifier_free_wifi_scan_shape_is_accepted_exactly(self):
        value = envelope(45, source="wifi", status="observed",
                         payload=wifi_scan_payload(), missing_reason=None)
        raw = frame(value)
        result = self.store.collection.ingest(raw, raw_record(raw), transport="wifi")
        self.assertEqual(result["result"], "accepted")
        self.assertEqual(result["delivery_ack"]["payload_sha256"], hashlib.sha256(raw).hexdigest())
        with self.store.connection() as db:
            stored = base64.b64decode(db.execute("SELECT raw_payload_b64 FROM raw_frames").fetchone()[0])
        self.assertEqual(stored, raw)

    def test_explicit_test_run_id_is_stored_and_old_frames_fall_back_to_session(self):
        explicit = envelope(75, session_id=None, test_run_id="field-020-run-20260916")
        legacy = envelope(76, session_id="legacy-session")
        nullable = envelope(77, session_id="nullable-fallback", test_run_id=None)
        for value in (explicit, legacy, nullable):
            self.assertEqual(self.ingest(value)["result"], "accepted")

        with self.store.connection() as db:
            stored = [
                tuple(row)
                for row in db.execute(
                    "SELECT frame_id,test_run_id FROM raw_frames ORDER BY id"
                ).fetchall()
            ]
        self.assertEqual(stored, [
            (explicit["observation_id"], "field-020-run-20260916"),
            (legacy["observation_id"], "legacy-session"),
            (nullable["observation_id"], "nullable-fallback"),
        ])

    def test_test_run_id_rejects_empty_unsafe_oversized_and_non_string_values(self):
        invalid_values = ("", "field run with spaces", "x" * 129, 17, {})
        for sequence, test_run_id in enumerate(invalid_values, 78):
            with self.subTest(test_run_id=test_run_id):
                with self.assertRaises(CollectionError) as raised:
                    self.ingest(envelope(sequence, test_run_id=test_run_id))
                self.assertEqual(raised.exception.code, "invalid_collection_envelope")
        self.assertEqual(self.table_counts(), (0, 0, 0))

    def test_bounded_firmware_provenance_is_allowed_without_opening_wifi_extensions(self):
        value = envelope(45, source="wifi", status="observed",
                         payload=wifi_scan_payload(), missing_reason=None)
        value["firmware_elf_sha256"] = FIRMWARE_ELF_SHA256
        value["test_run_id"] = "field-020-wifi-run"
        raw = frame(value)
        result = self.store.collection.ingest(raw, raw_record(raw), transport="wifi")
        self.assertEqual(result["result"], "accepted")
        with self.store.connection() as db:
            self.assertEqual(
                db.execute("SELECT test_run_id FROM raw_frames").fetchone()[0],
                "field-020-wifi-run",
            )

        unknown = envelope(46, source="wifi", status="observed",
                           payload=wifi_scan_payload(), missing_reason=None)
        unknown["firmware_elf_sha256"] = FIRMWARE_ELF_SHA256
        unknown["provenance_note"] = "not-allowlisted"
        unknown_raw = frame(unknown)
        with self.assertRaises(CollectionError) as raised:
            self.store.collection.ingest(
                unknown_raw, raw_record(unknown_raw), transport="wifi"
            )
        self.assertEqual(raised.exception.code, "collection_privacy_policy_rejected")

        malformed = envelope(47, source="wifi", status="observed",
                             payload=wifi_scan_payload(), missing_reason=None)
        malformed["firmware_elf_sha256"] = "AB" * 32
        malformed_raw = frame(malformed)
        with self.assertRaises(CollectionError) as raised:
            self.store.collection.ingest(
                malformed_raw, raw_record(malformed_raw), transport="wifi"
            )
        self.assertEqual(raised.exception.code, "invalid_collection_envelope")
        self.assertEqual(self.table_counts(), (1, 1, 1))

    def test_wifi_scan_shape_rejects_retention_true_extra_keys_and_bad_channel_items(self):
        invalid_payloads = (
            wifi_scan_payload(identifiers_retained=True),
            wifi_scan_payload(privacy_reason="identifier_policy_unknown"),
            wifi_scan_payload(unexpected_aggregate=1),
            wifi_scan_payload(channel_summary=[{"channel": 1, "ap_count": 1, "strongest_rssi": -41, "average_rssi": -50}], sampled_ap_count=1, total_seen=1),
            wifi_scan_payload(channel_summary=[{"channel": 15, "ap_count": 1, "strongest_rssi": -41}], sampled_ap_count=1, total_seen=1),
            wifi_scan_payload(channel_summary=[{"channel": 1, "ap_count": 1, "strongest_rssi": -128}], sampled_ap_count=1, total_seen=1),
            wifi_scan_payload(channel_summary=[
                {"channel": 1, "ap_count": 1, "strongest_rssi": -41},
                {"channel": 1, "ap_count": 2, "strongest_rssi": -52},
            ], sampled_ap_count=3, total_seen=3),
        )
        for sequence, payload in enumerate(invalid_payloads, 46):
            with self.subTest(sequence=sequence):
                with self.assertRaises(CollectionError) as raised:
                    self.ingest(envelope(sequence, source="wifi", status="observed",
                                         payload=payload, missing_reason=None))
                self.assertEqual(raised.exception.code, "collection_privacy_policy_rejected")
        self.assertEqual(self.table_counts(), (0, 0, 0))

    def test_privacy_guard_preserves_exact_raw_first_for_allowed_wifi_and_nonwifi(self):
        values = (
            (envelope(50, source="wifi", status="observed", missing_reason=None,
                      payload=wifi_scan_payload()), "wifi"),
            (envelope(51), "lte"),
        )
        raw_frames = []
        for value, transport in values:
            raw = frame(value)
            raw_frames.append(raw)
            result = self.store.collection.ingest(raw, raw_record(raw), transport=transport)
            self.assertEqual(result["result"], "accepted")
            self.assertEqual(result["delivery_ack"]["payload_sha256"], hashlib.sha256(raw).hexdigest())
        with self.store.connection() as db:
            stored = [base64.b64decode(row[0]) for row in
                      db.execute("SELECT raw_payload_b64 FROM raw_frames ORDER BY id")]
        self.assertEqual(stored, raw_frames)
        self.assertEqual(self.table_counts(), (2, 2, 2))

    def test_wifi_schema_enforces_privacy_shape_and_leaves_nonwifi_additive(self):
        schema_path = Path(__file__).resolve().parents[1] / "shared/contracts/collection_observation.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        legal = envelope(60, source="wifi", status="connected",
                         payload={"phase": "link_event", "connected": True}, missing_reason=None)
        self.assertEqual(list(validator.iter_errors(legal)), [])
        complete_scan = envelope(66, source="wifi", status="observed",
                                 payload=wifi_scan_payload(), missing_reason=None)
        self.assertEqual(list(validator.iter_errors(complete_scan)), [])
        firmware_provenance = envelope(74, source="wifi", status="observed",
                                       payload=wifi_scan_payload(), missing_reason=None)
        firmware_provenance["firmware_elf_sha256"] = FIRMWARE_ELF_SHA256
        firmware_provenance["test_run_id"] = "field-020-wifi-run"
        self.assertEqual(list(validator.iter_errors(firmware_provenance)), [])
        nullable_provenance = {**firmware_provenance, "test_run_id": None}
        self.assertEqual(list(validator.iter_errors(nullable_provenance)), [])
        for invalid in (
            envelope(61, source="wifi", payload={"bssid": "00:11:22:33:44:55"}),
            envelope(62, source="wifi", payload={"nested": {"SSID": "private"}}),
            {**envelope(63, source="wifi", payload={"connected": True}), "MaC": "00:11:22:33:44:55"},
            {**envelope(72, source="wifi", payload=wifi_scan_payload()), "wifi_bssid": "00:11:22:33:44:55"},
            envelope(64, source="wifi", payload={"aps": [{"rssi": -40}]}),
            envelope(67, source="wifi", payload=wifi_scan_payload(identifiers_retained=True)),
            envelope(71, source="wifi", payload=wifi_scan_payload(privacy_reason="identifier_policy_unknown")),
            envelope(68, source="wifi", payload=wifi_scan_payload(extra_field=False)),
            envelope(69, source="wifi", payload=wifi_scan_payload(
                channel_summary=[{"channel": 0, "ap_count": 1, "strongest_rssi": -50}],
                sampled_ap_count=1, total_seen=1)),
            envelope(70, source="wifi", payload=wifi_scan_payload(
                channel_summary=[{"channel": 6, "ap_count": 1, "strongest_rssi": -50, "extra": 1}],
                sampled_ap_count=1, total_seen=1)),
            envelope(73, source="wifi", payload=wifi_scan_payload(
                channel_summary=[
                    {"channel": 6, "ap_count": 1, "strongest_rssi": -50},
                    {"channel": 6, "ap_count": 2, "strongest_rssi": -60},
                ], sampled_ap_count=3, total_seen=3)),
            {**firmware_provenance, "firmware_elf_sha256": "AB" * 32},
            {**firmware_provenance, "test_run_id": "x" * 129},
            {**firmware_provenance, "test_run_id": "field run with spaces"},
            {**firmware_provenance, "provenance_note": "not-allowlisted"},
        ):
            self.assertTrue(list(validator.iter_errors(invalid)))
        nonwifi = envelope(65, source="device", status="observed", payload={"raw_diagnostic": "preserved"})
        self.assertEqual(list(validator.iter_errors(nonwifi)), [])

    def test_concurrent_retry_and_network_change_preserve_identity_and_one_raw_copy(self):
        value, raw = envelope(), frame(envelope())
        def attempt(index):
            return self.store.collection.ingest(raw, raw_record(raw), transport="wifi" if index % 2 else "lte")
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(attempt, range(20)))
        self.assertEqual(sum(result["result"] == "accepted" for result in results), 1)
        self.assertEqual(sum(result["result"] == "duplicate" for result in results), 19)
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_records").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_delivery_attempts").fetchone()[0], 20)
            self.assertEqual({row[0] for row in db.execute("SELECT claimed_actual_transport FROM collection_delivery_attempts")}, {"wifi", "lte"})
        self.assertEqual(len({result["delivery_ack"]["payload_sha256"] for result in results}), 1)

    def test_identity_conflict_retains_conflicting_bytes_but_has_no_positive_ack(self):
        value = envelope()
        self.ingest(value)
        changed = {**value, "missing_reason": "different immutable bytes"}
        with running_hub(self.store) as base:
            code, body, _ = http(base, f"/api/v1/devices/{DEVICE}/raw-ingest", body=frame(changed), token=UPLOAD_TOKEN, transport="lte")
        self.assertEqual(code, 409, body)
        self.assertNotIn("delivery_ack", json.loads(body))
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collection_records").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_frames").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT result FROM collection_delivery_attempts ORDER BY id DESC").fetchone()[0], "conflict")

    def test_index_failure_rolls_back_raw_and_delivery_and_does_not_ack(self):
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER fail_collection_insert BEFORE INSERT ON collection_records BEGIN SELECT RAISE(ABORT, 'test disk failure'); END")
        with running_hub(self.store) as base:
            code, body, _ = http(base, f"/api/v1/devices/{DEVICE}/raw-ingest", body=frame(envelope()), token=UPLOAD_TOKEN, transport="wifi")
        self.assertEqual(code, 500)
        self.assertNotIn("delivery_ack", json.loads(body))
        with self.store.connection() as db:
            for table in ("raw_frames", "collection_records", "collection_delivery_attempts"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)

    def test_authenticated_business_parse_failure_is_preserved_and_acknowledged(self):
        value = envelope(source="imu", status="observed", payload={"encoding": "offset_us+six_i16le+base64-v1", "sample_record_bytes": 16, "sample_count": 20, "samples_b64": "broken"})
        result = self.ingest(value)
        self.assertEqual(result["parse_status"], "parse_error")
        self.assertEqual(result["delivery_ack"]["status"], "accepted")
        restored = message_hub.MessageHubStore(self.store.db_path).collection.page(DEVICE, {}, raw=True)
        self.assertEqual(restored["records"][0]["envelope"]["payload"]["samples_b64"], "broken")
        self.assertEqual(restored["records"][0]["preview"]["sample_count"], 0)

    def test_imu_actual_offsets_and_raw_counts_are_complete(self):
        raw = b"".join(struct.pack("<I6h", i * 50_017, i, -i, 30000, -32768, 32767, 100) for i in range(20))
        payload = {"encoding": "offset_us+six_i16le+base64-v1", "sample_record_bytes": 16, "sample_count": 20, "samples_b64": base64.b64encode(raw).decode(), "requested_interval_us": 50000, "axis_mount": "unverified"}
        self.ingest(envelope(source="imu", status="observed", payload=payload))
        source = self.store.collection.summary(DEVICE)["sources"][0]
        self.assertEqual(source["samples"], 20)
        self.assertEqual(source["latest"]["preview"]["last_offset_us"], 19 * 50017)
        self.assertEqual(base64.b64decode(source["latest"]["envelope"]["payload"]["samples_b64"]), raw)

    def test_firmware_numeric_at_outcomes_partial_imu_and_stopped_attempts_are_preserved(self):
        value = envelope()
        value["payload"]["at"][0]["outcome"] = 0
        self.assertEqual(self.ingest(value)["parse_status"], "ok")
        stopped = envelope(2, status="stopped", payload={"at": [{"command": "AT+CGNSSPWR=0", "response": "\r\nOK\r\n", "outcome": 0, "elapsed_ms": 51}], "stopped": True})
        self.assertEqual(self.ingest(stopped)["parse_status"], "ok")
        empty = envelope(3, source="imu", status="partial", payload={"encoding": "offset_us+six_i16le+base64-v1", "sample_record_bytes": 16, "sample_count": 0, "samples_b64": "", "read_errors": 20})
        self.assertEqual(self.ingest(empty)["parse_status"], "ok")
        partial = envelope(4, source="imu", status="partial", payload={**empty["payload"], "sample_count": 1, "samples_b64": base64.b64encode(struct.pack("<I6h", 0, 1, 2, 3, 4, 5, 6)).decode()})
        self.assertEqual(self.ingest(partial)["parse_status"], "ok")
        source = next(item for item in self.store.collection.summary(DEVICE)["sources"] if item["source"] == "imu")
        self.assertEqual(source["samples"], 1)
        self.assertEqual(source["errors"], 2)

    def test_per_sensor_status_survives_other_sources_and_older_backfill(self):
        self.ingest(envelope(10, source="source_status", status="unavailable", payload={"source": "imu", "enabled": True, "state": "unavailable"}))
        self.ingest(envelope(11, source="source_status", status="running", payload={"source": "gnss", "enabled": True, "state": "running"}))
        self.ingest(envelope(1, source="source_status", status="running", payload={"source": "imu", "enabled": True, "state": "running"}))
        states = self.store.collection.summary(DEVICE)["source_states"]
        self.assertEqual(states["imu"]["envelope"]["status"], "unavailable")
        self.assertEqual(states["gnss"]["envelope"]["status"], "running")

    def test_old_backfill_never_overwrites_newer_source_event_state(self):
        self.ingest(envelope(10, status="observed", timestamp_utc="2026-09-06T02:00:10Z"))
        self.ingest(envelope(1, status="no_fix", timestamp_utc="2026-09-06T02:00:01Z"), "lte")
        summary = self.store.collection.summary(DEVICE)
        self.assertEqual(summary["sources"][0]["latest"]["envelope"]["sequence_id"], 10)
        self.assertEqual(summary["last_contact"]["observation_id"], "test-b1-1")
        self.assertEqual(summary["last_contact"]["claimed_actual_transport"], "lte")

    def test_bound_authorization_precedes_reads_and_raw_does_not_leak_to_legacy_api(self):
        self.ingest(envelope())
        with running_hub(self.store) as base:
            for suffix in ("summary", "records", "export.jsonl"):
                path = f"/api/v1/devices/{DEVICE}/collection/{suffix}"
                self.assertEqual(http(base, path)[0], 401)
                self.assertEqual(http(base, path, token=UPLOAD_TOKEN)[0], 401)
                self.assertEqual(http(base, path.replace(DEVICE, "other-device"), token=PROJECT_TOKEN)[0], 403)
            code, body, _ = http(base, f"/api/v1/devices/{DEVICE}/raw-frames", token=UPLOAD_TOKEN)
            self.assertEqual(code, 200)
            self.assertNotIn("CGNSSINFO", body.decode())
            self.assertNotIn("data", json.loads(body)["raw_frames"][0]["raw_payload"])
        with running_hub(self.store, binding=False) as base:
            self.assertEqual(http(base, f"/api/v1/devices/{DEVICE}/collection/summary", token=UPLOAD_TOKEN)[0], 503)

    def test_missing_ingest_auth_or_transport_is_not_accepted(self):
        with running_hub(self.store, token=None) as base:
            code, _, _ = http(base, f"/api/v1/devices/{DEVICE}/raw-ingest", body=frame(envelope()), transport="wifi")
            self.assertEqual(code, 503)
        with running_hub(self.store) as base:
            self.assertEqual(http(base, f"/api/v1/devices/{DEVICE}/raw-ingest", body=frame(envelope()), token=UPLOAD_TOKEN)[0], 422)
            self.assertEqual(http(base, f"/api/v1/devices/{DEVICE}/raw-ingest", body=frame(envelope()), transport="wifi")[0], 401)

    def test_route_frame_identity_crc_and_json_duplicate_members_are_rejected(self):
        good = envelope()
        for changed in ({**good, "device_id": "different"}, {**good, "timestamp_monotonic_ns": True}, {**good, "source": []}):
            with self.assertRaises(CollectionError):
                self.ingest(changed)
        raw = frame(good)
        with self.assertRaises(CollectionError):
            self.store.collection.ingest(raw[:-1]+b"x", raw_record(raw[:-1]+b"x"), transport="wifi")
        payload = json.dumps(good)[:-1] + ',"sequence_id":2}'
        duplicate = message_hub.build_raw_frame("event", good["observation_id"], payload.encode(), seq=1, content_type=CONTENT_TYPE)
        with self.assertRaises(CollectionError):
            self.store.collection.ingest(duplicate, raw_record(duplicate), transport="wifi")


class CollectionExportTests(unittest.TestCase):
    def test_byte_limited_pages_make_progress_and_keep_every_complete_large_record(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            for i in range(1, 21):
                raw = frame(envelope(i, source="device", status="observed", payload={"test_padding": "x" * 50000}))
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
            ids, cursor, pages = [], None, 0
            while True:
                query = {"page_size": ["100"]}
                if cursor:
                    query["cursor"] = [cursor]
                page = store.collection.page(DEVICE, query, raw=True)
                pages += 1
                self.assertLessEqual(page["page"]["bytes"], 2_000_000)
                self.assertTrue(page["records"] or page["delivery_attempts"])
                ids.extend(item["envelope"]["sequence_id"] for item in page["records"])
                if page["page"]["exhausted"]:
                    break
                self.assertNotEqual(cursor, page["page"]["next_cursor"])
                cursor = page["page"]["next_cursor"]
                self.assertLess(pages, 10)
            self.assertGreater(pages, 1)
            self.assertEqual(ids, list(range(1, 21)))

    def test_utc_filter_compares_time_not_iso_fraction_string_spelling(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            for i, utc in enumerate(("2026-09-06T02:00:00Z", "2026-09-06T02:00:00.100Z", "2026-09-06T02:00:00.900000Z"), 1):
                raw = frame(envelope(i, timestamp_utc=utc))
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
            page = store.collection.page(DEVICE, {"from_utc": ["2026-09-06T02:00:00.050Z"], "to_utc": ["2026-09-06T02:00:00.500Z"]})
            self.assertEqual([item["envelope"]["sequence_id"] for item in page["records"]], [2])
            self.assertEqual(page["records"][0]["envelope"]["timestamp_utc"], "2026-09-06T02:00:00.100Z")

    def test_snapshot_pagination_exports_all_raw_bytes_plus_context_without_small_history_limit(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            originals = {}
            for i in range(1, 208):
                value = envelope(i, source="time_anchor" if i == 1 else "gnss")
                raw = frame(value)
                originals[value["observation_id"]] = raw
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
            query = {"page_size": ["37"], "source": ["gnss"]}
            records, cursor = [], None
            while True:
                if cursor:
                    query["cursor"] = [cursor]
                page = store.collection.page(DEVICE, query, raw=True)
                records.extend(page["records"])
                if len(records) == 37:
                    raw = frame(envelope(999))
                    store.collection.ingest(raw, raw_record(raw), transport="wifi")
                if page["page"]["exhausted"]:
                    break
                cursor = page["page"]["next_cursor"]
            self.assertEqual(len(records), 207)
            self.assertEqual(len({r["envelope"]["observation_id"] for r in records}), 207)
            self.assertEqual(records[0]["envelope"]["source"], "time_anchor")
            for item in records:
                self.assertEqual(base64.b64decode(item["raw_frame"]["raw_payload"]["data"]), originals[item["envelope"]["observation_id"]])
            with self.assertRaises(CollectionError):
                store.collection.page(DEVICE, {"cursor": [cursor], "source": ["imu"]}, raw=True)

    def test_jsonl_http_has_manifest_and_original_observation_not_redacted(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            raw = frame(envelope())
            store.collection.ingest(raw, raw_record(raw), transport="wifi")
            with running_hub(store) as base:
                code, body, headers = http(base, f"/api/v1/devices/{DEVICE}/collection/export.jsonl", token=PROJECT_TOKEN)
            self.assertEqual(code, 200)
            rows = [json.loads(line) for line in body.splitlines()]
            self.assertEqual(rows[0]["kind"], "collection_export_manifest")
            schema_path = Path(__file__).resolve().parents[1] / "shared/contracts/collection_observation.schema.json"
            self.assertEqual(rows[0]["schema"]["sha256"], hashlib.sha256(schema_path.read_bytes()).hexdigest())
            self.assertEqual(rows[0]["schema"]["document"], json.loads(schema_path.read_text(encoding="utf-8")))
            self.assertTrue(rows[0]["page"]["exhausted"])
            self.assertEqual(base64.b64decode(rows[1]["raw_frame"]["raw_payload"]["data"]), raw)
            self.assertEqual(headers["Cache-Control"], "no-store")

    def test_annotation_is_bound_separate_idempotent_and_all_metadata_exported(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            original = envelope()
            raw = frame(original)
            store.collection.ingest(raw, raw_record(raw), transport="wifi")
            body = {"annotation_id": "annotation-test-1", "session_id": "test-session", "scene": "walking indoors", "wearing": "chest", "note": "test marker", "boot_count": None, "timestamp_monotonic_ns": None}
            encoded = json.dumps(body).encode()
            with running_hub(store) as base:
                path = f"/api/v1/devices/{DEVICE}/collection/annotations"
                self.assertEqual(http(base, path, body=encoded, token=UPLOAD_TOKEN)[0], 401)
                self.assertEqual(http(base, path.replace(DEVICE, "other-device"), body=encoded, token=PROJECT_TOKEN)[0], 403)
                code, result, _ = http(base, path, body=encoded, token=PROJECT_TOKEN)
                self.assertEqual(code, 200, result)
                annotation = json.loads(result)["annotation"]
                self.assertEqual(annotation["source"], "operator_annotation")
                self.assertEqual(annotation["time_reference_quality"], "no_device_clock_reference")
                code, repeated, _ = http(base, path, body=encoded, token=PROJECT_TOKEN)
                self.assertEqual(json.loads(repeated)["annotation"]["server_annotation_time"], annotation["server_annotation_time"])
                self.assertEqual(json.loads(repeated)["result"], "duplicate")
                conflict = json.dumps({**body, "note": "changed"}).encode()
                self.assertEqual(http(base, path, body=conflict, token=PROJECT_TOKEN)[0], 409)
            cursor, exported, annotations, deliveries = None, [], [], []
            while True:
                query = {"page_size": ["1"]}
                if cursor:
                    query["cursor"] = [cursor]
                page = store.collection.page(DEVICE, query, raw=True)
                exported += page["records"]
                annotations += page["annotations"]
                deliveries += page["delivery_attempts"]
                if page["page"]["exhausted"]:
                    break
                cursor = page["page"]["next_cursor"]
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["envelope"], original)
            self.assertEqual(len(annotations), 1)
            self.assertEqual(annotations[0]["scene"], body["scene"])
            self.assertEqual(len(deliveries), 1)
            self.assertEqual(deliveries[0]["claimed_actual_transport"], "wifi")

    def test_annotation_references_remain_unsynchronized_and_unknown_sessions_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            body = {"annotation_id": "annotation-test-1", "session_id": None, "scene": "outdoors", "wearing": "", "note": "", "boot_count": 7, "timestamp_monotonic_ns": 6000}
            result = store.collection.annotate(DEVICE, json.dumps(body).encode(), operator_id="test-project")
            self.assertEqual(result["annotation"]["time_reference_quality"], "operator_entered_unsynchronized")
            with self.assertRaises(CollectionError):
                store.collection.annotate(DEVICE, json.dumps({**body, "annotation_id": "new", "session_id": "unknown-session"}).encode(), operator_id="test-project")
            with self.assertRaises(CollectionError):
                store.collection.annotate(DEVICE, json.dumps({**body, "annotation_id": "new", "boot_count": None}).encode(), operator_id="test-project")

    def test_boot_without_utc_export_includes_later_time_anchor_and_freezes_annotation_and_receipt_streams(self):
        with tempfile.TemporaryDirectory() as root:
            store = message_hub.MessageHubStore(Path(root) / "hub.db")
            for value in (envelope(), envelope(2, source="time_anchor", status="observed", payload={"timestamp_monotonic_ns": 2000000000, "utc_ms": 1788650000000, "source": "sntp", "uncertainty_ms": None})):
                raw = frame(value)
                store.collection.ingest(raw, raw_record(raw), transport="wifi")
            query = {"page_size": ["1"], "source": ["gnss"]}
            first = store.collection.page(DEVICE, query, raw=True)
            self.assertIsNone(first["records"][0]["envelope"]["timestamp_utc"])
            late_note = {"annotation_id": "late", "session_id": None, "scene": "after snapshot", "wearing": "", "note": "", "boot_count": None, "timestamp_monotonic_ns": None}
            store.collection.annotate(DEVICE, json.dumps(late_note).encode(), operator_id="test-project")
            raw = frame(envelope())
            store.collection.ingest(raw, raw_record(raw), transport="lte")
            records, annotations, attempts = first["records"], [], []
            cursor = first["page"]["next_cursor"]
            while cursor:
                page = store.collection.page(DEVICE, {**query, "cursor": [cursor]}, raw=True)
                records += page["records"]
                annotations += page["annotations"]
                attempts += page["delivery_attempts"]
                cursor = page["page"]["next_cursor"]
            self.assertEqual([r["envelope"]["source"] for r in records], ["gnss", "time_anchor"])
            self.assertEqual(annotations, [])
            self.assertEqual(len(attempts), 2)
            self.assertTrue(all(item["claimed_actual_transport"] == "wifi" for item in attempts))


if __name__ == "__main__":
    unittest.main()
