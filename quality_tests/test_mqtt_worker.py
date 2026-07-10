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


def telemetry_payload(event_type: str = "sos_pressed", seq: int = 8) -> str:
    return json.dumps(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "device_id": "ego-link-001",
            "ts": "2026-06-20T10:00:00+00:00",
            "seq": seq,
            "message_type": "event",
            "event_type": event_type,
            "priority": "critical" if event_type == "sos_pressed" else "normal",
            "source": "unit_test",
            "battery": 86,
        },
        separators=(",", ":"),
    )


def ack_payload(seq: int = 9) -> str:
    return json.dumps(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "device_id": "ego-link-001",
            "ts": "2026-06-20T10:00:01+00:00",
            "seq": seq,
            "message_type": "ack",
            "cmd_id": "cmd-0001",
            "status": "ok",
        },
        separators=(",", ":"),
    )


class MqttWorkerTests(unittest.TestCase):
    def test_build_subscribe_command_uses_verbose_output(self) -> None:
        command = mqtt_worker.build_subscribe_command(
            host="192.168.31.250",
            port=1883,
            topics=["ego/link/+/status"],
            executable="mosquitto_sub.exe",
            max_messages=1,
            wait_seconds=5,
        )

        self.assertEqual(command[:6], ["mosquitto_sub.exe", "-h", "192.168.31.250", "-p", "1883", "-v"])
        self.assertIn("-v", command)
        self.assertIn("ego/link/+/status", command)
        self.assertIn("-C", command)
        self.assertIn("1", command)
        self.assertIn("-W", command)
        self.assertIn("5", command)

    def test_default_subscribe_command_includes_status_event_and_ack(self) -> None:
        command = mqtt_worker.build_subscribe_command(executable="mosquitto_sub.exe")

        self.assertEqual(command.count("-t"), 3)
        self.assertIn("ego/link/+/status", command)
        self.assertIn("ego/link/+/event", command)
        self.assertIn("ego/link/+/ack", command)

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

    def test_event_from_payload_accepts_device_event(self) -> None:
        event = mqtt_worker.event_from_payload(
            "ego/link/ego-link-001/event",
            telemetry_payload("sos_pressed"),
            received_at="2026-06-20T00:00:00+00:00",
        )

        self.assertEqual(event["message_type"], "event")
        self.assertEqual(event["event_type"], "sos_pressed")
        self.assertEqual(event["priority"], "critical")
        self.assertEqual(event["direction"], "uplink")
        self.assertEqual(event["mqtt_topic"], "ego/link/ego-link-001/event")

    def test_event_from_payload_accepts_ack(self) -> None:
        event = mqtt_worker.event_from_payload(
            "ego/link/ego-link-001/ack",
            ack_payload(),
            received_at="2026-06-20T00:00:00+00:00",
        )

        self.assertEqual(event["message_type"], "ack")
        self.assertEqual(event["event_type"], "mqtt_ack")
        self.assertEqual(event["cmd_id"], "cmd-0001")
        self.assertEqual(event["status"], "ok")

    def test_consume_lines_writes_jsonl_and_skips_bad_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            errors = io.StringIO()

            stored = mqtt_worker.consume_lines(
                [
                    f"ego/link/ego-link-001/status {status_payload(seq=1)}",
                    "bad-line-without-payload",
                    f"ego/link/ego-link-001/event {telemetry_payload(seq=2)}",
                    f"ego/link/ego-link-001/ack {ack_payload(seq=3)}",
                ],
                log_path,
                now=lambda: "2026-06-20T00:00:00+00:00",
                errors=errors,
            )
            rows = event_store.load_recent(log_path, limit=5)

        self.assertEqual(stored, 3)
        self.assertEqual([row["seq"] for row in rows], [3, 2, 1])
        self.assertEqual([row["event_type"] for row in rows], ["mqtt_ack", "sos_pressed", "mqtt_status"])
        self.assertIn("skipped line", errors.getvalue())

    def test_consume_lines_calls_after_store_for_valid_events_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            calls: list[tuple[str, Path]] = []

            stored = mqtt_worker.consume_lines(
                [
                    f"ego/link/ego-link-001/status {status_payload(seq=1)}",
                    "bad-line-without-payload",
                    f"ego/link/ego-link-001/event {telemetry_payload(seq=2)}",
                ],
                log_path,
                now=lambda: "2026-06-20T00:00:00+00:00",
                after_store=lambda event, path: calls.append((event["event_type"], path)),
            )

        self.assertEqual(stored, 2)
        self.assertEqual(calls, [("mqtt_status", log_path), ("sos_pressed", log_path)])

    def test_consume_lines_logs_after_store_failure_and_keeps_ingesting(self) -> None:
        def fail_after_store(_event: dict[str, object], _path: Path) -> None:
            raise RuntimeError("synthetic safety failure")

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            errors = io.StringIO()

            stored = mqtt_worker.consume_lines(
                [f"ego/link/ego-link-001/event {telemetry_payload(seq=2)}"],
                log_path,
                now=lambda: "2026-06-20T00:00:00+00:00",
                errors=errors,
                after_store=fail_after_store,
            )
            rows = event_store.load_recent(log_path, limit=5)

        self.assertEqual(stored, 1)
        self.assertEqual(rows[0]["event_type"], "sos_pressed")
        self.assertIn("safety processing failed", errors.getvalue())

    def test_make_safety_after_store_processes_log_and_reports_summary(self) -> None:
        original = mqtt_worker.process_safety_log
        calls: list[tuple[Path, int]] = []

        def fake_process_safety_log(event_log: Path, *, limit: int = 20) -> dict[str, object]:
            calls.append((event_log, limit))
            return {
                "processed": 1,
                "summary": {
                    "safety_evaluations": 1,
                    "safety_events": 1,
                    "base_commands": 1,
                },
            }

        try:
            mqtt_worker.process_safety_log = fake_process_safety_log  # type: ignore[assignment]
            progress = io.StringIO()
            log_path = Path("runtime/events.jsonl")
            after_store = mqtt_worker.make_safety_after_store(limit=7, progress=progress)

            after_store({"event_type": "sos_pressed"}, log_path)
        finally:
            mqtt_worker.process_safety_log = original  # type: ignore[assignment]

        self.assertEqual(calls, [(log_path, 7)])
        self.assertIn("processed 1 source event", progress.getvalue())
        self.assertIn("base_commands=1", progress.getvalue())

    def test_parse_args_enables_supervised_safety_processing(self) -> None:
        args = mqtt_worker.parse_args(["--process-safety", "--safety-process-limit", "7"])

        self.assertTrue(args.process_safety)
        self.assertEqual(args.safety_process_limit, 7)


if __name__ == "__main__":
    unittest.main()
