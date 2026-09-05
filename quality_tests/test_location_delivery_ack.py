from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib import error

from jsonschema import Draft202012Validator

from quality_tests.test_location_state_http import running_hub
from quality_tests.test_location_state_mirror import envelope, location_state
from quality_tests.test_message_hub_server import post_json
from server.location_delivery_ack import (
    ACK_CONTRACT_VERSION,
    LocationDeliveryAckError,
    build_location_state_delivery_ack,
    exact_payload_sha256,
    location_outbox_event_id,
)
from server.location_state_runtime import LocationStateRuntimeMirror


ROOT = Path(__file__).resolve().parents[1]
OUTBOX_SCHEMA = json.loads(
    (ROOT / "shared" / "contracts" / "persistent_priority_outbox_v0.schema.json")
    .read_text(encoding="utf-8")
)
ACK_SCHEMA = {"$ref": "#/$defs/ack", "$defs": OUTBOX_SCHEMA["$defs"]}


class LocationDeliveryAckTests(unittest.TestCase):
    def setUp(self) -> None:
        seed = LocationStateRuntimeMirror()
        self.envelope = envelope(seed, location_state(1_000))
        self.envelope.pop("server_receive_time_ms", None)
        self.identity = {
            field: self.envelope[field]
            for field in (
                "device_id",
                "boot_count",
                "session_id",
                "event_time_ms",
                "sequence_id",
                "observation_id",
            )
        }
        self.result = {"status": "accepted", "identity": self.identity}

    def test_ack_binds_exact_bytes_and_is_safe_and_deterministic(self) -> None:
        compact = json.dumps(
            self.envelope, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        spaced = json.dumps(self.envelope, sort_keys=True, indent=2).encode("utf-8")
        first = build_location_state_delivery_ack(
            compact, self.envelope, self.result, ack_time_ms=2_000
        )
        repeated = build_location_state_delivery_ack(
            compact,
            self.envelope,
            {**self.result, "status": "duplicate"},
            ack_time_ms=2_001,
        )
        different_bytes = build_location_state_delivery_ack(
            spaced, self.envelope, self.result, ack_time_ms=2_002
        )

        digest = hashlib.sha256(compact).hexdigest()
        self.assertEqual(ACK_CONTRACT_VERSION, first["contract_version"])
        self.assertEqual(digest, first["payload_sha256"])
        self.assertEqual("loc-" + digest, first["event_id"])
        self.assertEqual("ack-" + digest, first["ack_id"])
        self.assertEqual([], list(Draft202012Validator(ACK_SCHEMA).iter_errors(first)))
        self.assertEqual(first["event_id"], repeated["event_id"])
        self.assertNotEqual(first["event_id"], different_bytes["event_id"])
        self.assertEqual(digest, exact_payload_sha256(compact))
        self.assertEqual(first["event_id"], location_outbox_event_id(digest))

    def test_ack_rejects_nonaccepted_or_mismatched_ingest_result(self) -> None:
        payload = json.dumps(self.envelope).encode("utf-8")
        with self.assertRaisesRegex(LocationDeliveryAckError, "durably accepted"):
            build_location_state_delivery_ack(
                payload,
                self.envelope,
                {**self.result, "status": "rejected"},
                ack_time_ms=2_000,
            )
        for field, replacement in (
            ("device_id", "other-device"),
            ("observation_id", "other-observation"),
            ("sequence_id", 99),
        ):
            bad = deepcopy(self.result)
            bad["identity"] = {**bad["identity"], field: replacement}
            with self.subTest(field=field):
                with self.assertRaisesRegex(LocationDeliveryAckError, "mismatch"):
                    build_location_state_delivery_ack(
                        payload,
                        self.envelope,
                        bad,
                        ack_time_ms=2_000,
                    )

    def test_ack_rejects_ids_that_cannot_enter_the_durable_outbox_contract(self) -> None:
        item = deepcopy(self.envelope)
        item["device_id"] = "设备-一"
        item["session_id"] = "会话-一"
        item["observation_id"] = "观测-一"
        result = {
            "status": "accepted",
            "identity": {
                field: item[field]
                for field in (
                    "device_id",
                    "boot_count",
                    "session_id",
                    "event_time_ms",
                    "sequence_id",
                    "observation_id",
                )
            },
        }
        payload = json.dumps(item, ensure_ascii=False).encode("utf-8")
        with self.assertRaisesRegex(LocationDeliveryAckError, "outbox-safe"):
            build_location_state_delivery_ack(
                payload, item, result, ack_time_ms=2_000
            )

    def test_http_ingest_returns_positive_ack_only_after_durable_accept(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            headers = {"Authorization": "Bearer secret"}
            with running_hub(db_path) as base:
                accepted = post_json(
                    base, "/api/v1/location-states", self.envelope, headers
                )
                duplicate = post_json(
                    base, "/api/v1/location-states", self.envelope, headers
                )

            self.assertEqual("accepted", accepted["result"]["status"])
            self.assertEqual("duplicate", duplicate["result"]["status"])
            self.assertEqual(
                "server_durable_ingest_only", accepted["delivery_scope"]
            )
            first_ack = accepted["delivery_ack"]
            second_ack = duplicate["delivery_ack"]
            self.assertEqual("accepted", first_ack["status"])
            expected_wire_bytes = json.dumps(self.envelope).encode("utf-8")
            self.assertEqual(
                hashlib.sha256(expected_wire_bytes).hexdigest(),
                first_ack["payload_sha256"],
            )
            self.assertEqual(first_ack["event_id"], second_ack["event_id"])
            self.assertEqual(
                first_ack["payload_sha256"], second_ack["payload_sha256"]
            )
            response_text = json.dumps(accepted, sort_keys=True)
            for private_field in ("latitude_deg", "longitude_deg", "last_trusted_location"):
                self.assertNotIn(private_field, response_text)

    def test_http_rejects_outbox_incompatible_identity_before_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.db"
            item = deepcopy(self.envelope)
            item["device_id"] = "设备-一"
            with running_hub(db_path) as base:
                with self.assertRaises(error.HTTPError) as rejected:
                    post_json(
                        base,
                        "/api/v1/location-states",
                        item,
                        {"Authorization": "Bearer secret"},
                    )
                response = json.loads(rejected.exception.read().decode("utf-8"))
                rejected.exception.close()
                self.assertEqual(422, rejected.exception.code)
                self.assertEqual("invalid_location_state", response["error"])
                self.assertNotIn("设备", json.dumps(response, ensure_ascii=False))
            with closing(sqlite3.connect(db_path)) as database:
                self.assertEqual(
                    0,
                    database.execute(
                        "SELECT COUNT(*) FROM location_state_timeline"
                    ).fetchone()[0],
                )


if __name__ == "__main__":
    unittest.main()
