from __future__ import annotations

import json
from pathlib import Path
import unittest

from pc_simulator import protocol


MESSAGE_HUB_SCHEMAS = {
    "status": "message_hub_status.schema.json",
    "event": "message_hub_event.schema.json",
    "command": "message_hub_command.schema.json",
    "ack": "message_hub_ack.schema.json",
    "error": "message_hub_error.schema.json",
}

RAW_FRAME_SCHEMA = "message_hub_raw_frame_record.schema.json"


class MessageHubContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.contract_dir = self.repo_root / "shared" / "contracts"

    def load_schema(self, name: str) -> dict:
        path = self.contract_dir / name
        self.assertTrue(path.is_file(), f"Missing message-hub schema: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_message_hub_schemas_are_valid_json_schema_files(self) -> None:
        for name in MESSAGE_HUB_SCHEMAS.values():
            with self.subTest(schema=name):
                schema = self.load_schema(name)

            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["type"], "object")
            self.assertTrue(schema["$id"].endswith(name))

    def test_message_hub_schemas_use_current_protocol_version(self) -> None:
        for message_type, name in MESSAGE_HUB_SCHEMAS.items():
            with self.subTest(schema=name):
                schema = self.load_schema(name)

            self.assertEqual(schema["properties"]["protocol_version"]["const"], protocol.PROTOCOL_VERSION)
            self.assertEqual(schema["properties"]["message_type"]["const"], message_type)

    def test_current_pc_simulator_builders_match_required_fields(self) -> None:
        examples = {
            "status": protocol.status_message(
                "ego-link-001",
                "2026-06-27T00:00:00Z",
                1,
                battery=87,
                link_type="mock_4g_over_wifi",
                guard_mode="child_safety",
                queue_size=0,
            ),
            "event": protocol.event_message(
                "ego-link-001",
                "2026-06-27T00:00:01Z",
                2,
                "sensor_sample",
                "normal",
                source="unit_test",
            ),
            "command": protocol.command_message("cmd-0001", "set_report_interval", device_id="ego-link-001"),
            "ack": protocol.ack_message("ego-link-001", "2026-06-27T00:00:02Z", 3, "cmd-0001", "ok"),
        }

        for message_type, example in examples.items():
            with self.subTest(message_type=message_type):
                schema = self.load_schema(MESSAGE_HUB_SCHEMAS[message_type])

            for field in schema["required"]:
                self.assertIn(field, example)

            self.assertEqual(example["protocol_version"], protocol.PROTOCOL_VERSION)
            self.assertEqual(example["message_type"], message_type)

    def test_message_hub_schemas_allow_optional_test_run_id(self) -> None:
        for name in MESSAGE_HUB_SCHEMAS.values():
            with self.subTest(schema=name):
                schema = self.load_schema(name)

            self.assertIn("test_run_id", schema["properties"])
            self.assertEqual(schema["properties"]["test_run_id"]["type"], "string")
            self.assertEqual(schema["properties"]["test_run_id"]["minLength"], 1)

    def test_status_and_event_contracts_expose_optional_observability_fields(self) -> None:
        expected = {
            "boot_id",
            "uptime_s",
            "transport",
            "runtime",
            "command",
            "power",
            "gnss",
            "cell",
            "lte",
        }
        for name in (MESSAGE_HUB_SCHEMAS["status"], MESSAGE_HUB_SCHEMAS["event"]):
            with self.subTest(schema=name):
                schema = self.load_schema(name)

            self.assertTrue(expected.issubset(schema["properties"]))
            self.assertTrue(expected.isdisjoint(schema["required"]))

        event_schema = self.load_schema(MESSAGE_HUB_SCHEMAS["event"])
        self.assertIn("wifi", event_schema["properties"])
        self.assertIn("imu", event_schema["properties"])
        self.assertIn("location_belief", event_schema["properties"])
        self.assertNotIn("wifi", event_schema["required"])
        self.assertNotIn("imu", event_schema["required"])
        self.assertNotIn("location_belief", event_schema["required"])

    def test_error_contract_requires_diagnosable_error_fields(self) -> None:
        schema = self.load_schema(MESSAGE_HUB_SCHEMAS["error"])

        self.assertIn("error_code", schema["required"])
        self.assertIn("severity", schema["required"])
        self.assertEqual(schema["properties"]["error_code"]["pattern"], "^[A-Z0-9_]+$")

    def test_raw_frame_record_contract_preserves_raw_bytes_before_parse(self) -> None:
        schema = self.load_schema(RAW_FRAME_SCHEMA)

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["type"], "object")
        self.assertTrue(schema["$id"].endswith(RAW_FRAME_SCHEMA))
        self.assertEqual(schema["properties"]["protocol_version"]["const"], protocol.PROTOCOL_VERSION)
        self.assertEqual(schema["properties"]["transport_profile"]["const"], "raw-frame.p0.v1")

        required = set(schema["required"])
        self.assertIn("raw_payload", required)
        self.assertIn("parse_result", required)
        self.assertIn("server_received_at", required)

        raw_payload = schema["properties"]["raw_payload"]
        self.assertIn("sha256", raw_payload["required"])
        self.assertIn("byte_len", raw_payload["required"])

        parse_statuses = schema["properties"]["parse_result"]["properties"]["status"]["enum"]
        self.assertIn("ok", parse_statuses)
        self.assertIn("partial", parse_statuses)
        self.assertIn("checksum_failed", parse_statuses)
        self.assertIn("malformed", parse_statuses)


if __name__ == "__main__":
    unittest.main()
