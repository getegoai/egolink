from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import event_store, mqtt_worker, protocol


def status_payload(seq: int = 7) -> str:
    return json.dumps(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "device_id": "ego-link-001",
            "ts": "uptime_ms:12345",
            "seq": seq,
            "message_type": "status",
            "battery": 87,
            "link_type": "mock_4g_over_wifi",
            "guard_mode": "child_safety",
            "queue_size": 0,
        },
        separators=(",", ":"),
    )


class MqttWorkerTests(unittest.TestCase):
    def test_build_subscribe_command_uses_verbose_output(self) -> None:
        command = mqtt_worker.build_subscribe_command(
            host="192.168.31.250",
            port=1883,
            topic="ego/link/+/status",
            executable="mosquitto_sub.exe",
            max_messages=1,
            wait_seconds=5,
        )

        self.assertEqual(command[:7], ["mosquitto_sub.exe", "-h", "192.168.31.250", "-p", "1883", "-t", "ego/link/+/status"])
        self.assertIn("-v", command)
        self.assertIn("-C", command)
        self.assertIn("1", command)
        self.assertIn("-W", command)
        self.assertIn("5", command)

    def test_parse_verbose_line_splits_topic_and_payload(self) -> None:
        topic, payload = mqtt_worker.parse_verbose_line(
            f"ego/link/ego-link-001/status {status_payload()}"
        )

        self.assertEqual(topic, "ego/link/ego-link-001/status")
        self.assertEqual(json.loads(payload)["message_type"], "status")

    def test_status_event_from_payload_preserves_device_status(self) -> None:
        event = mqtt_worker.status_event_from_payload(
            "ego/link/ego-link-001/status",
            status_payload(),
            received_at="2026-06-20T00:00:00+00:00",
        )

        self.assertEqual(event["event_type"], "mqtt_status")
        self.assertEqual(event["mqtt_topic"], "ego/link/ego-link-001/status")
        self.assertEqual(event["ingest_source"], "pc_simulator.mqtt_worker")
        self.assertEqual(event["device_id"], "ego-link-001")
        self.assertEqual(event["battery"], 87)

    def test_status_event_rejects_non_status_payload(self) -> None:
        payload = json.dumps({"message_type": "event"})

        with self.assertRaises(mqtt_worker.MqttWorkerError):
            mqtt_worker.status_event_from_payload("ego/link/ego-link-001/event", payload)

    def test_consume_lines_writes_jsonl_and_skips_bad_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            errors = io.StringIO()

            stored = mqtt_worker.consume_lines(
                [
                    f"ego/link/ego-link-001/status {status_payload(seq=1)}",
                    "bad-line-without-payload",
                    f"ego/link/ego-link-001/status {status_payload(seq=2)}",
                ],
                log_path,
                now=lambda: "2026-06-20T00:00:00+00:00",
                errors=errors,
            )
            rows = event_store.load_recent(log_path, limit=5)

        self.assertEqual(stored, 2)
        self.assertEqual([row["seq"] for row in rows], [2, 1])
        self.assertIn("skipped line", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
