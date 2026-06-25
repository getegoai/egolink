from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pc_simulator import board_bridge, session_inspector, session_recorder
from scripts import board_bridge as board_bridge_cli


def j(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class BoardBridgeTests(unittest.TestCase):
    def test_hello_binds_roles_and_motion_routes_commands(self) -> None:
        times = iter(
            [
                "2026-06-23T10:00:00+00:00",
                "2026-06-23T10:00:01+00:00",
                "2026-06-23T10:00:02+00:00",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            event_log = Path(tmp) / "events.jsonl"
            result = board_bridge.consume_named_sources(
                {
                    "wearable_boot": [
                        j(
                            {
                                "type": "hello",
                                "device_id": "wearable-node-001",
                                "role": "wearable_node",
                                "protocol_version": "0.1",
                            }
                        )
                    ],
                    "connectivity_boot": [
                        j(
                            {
                                "type": "hello",
                                "device_id": "connectivity-node-001",
                                "role": "connectivity_node",
                                "protocol_version": "0.1",
                            }
                        )
                    ],
                    "wearable_live": [
                        j(
                            {
                                "source": "wearable-node-001",
                                "type": "motion_event",
                                "seq": 1024,
                                "timestamp_ms": 1782210408000,
                                "payload": {
                                    "impact_score": 0.92,
                                    "fall_score": 0.78,
                                    "stationary_seconds": 12,
                                },
                            }
                        )
                    ],
                },
                event_log,
                now=lambda: next(times),
            )
            rows = read_jsonl(event_log)

        self.assertEqual(result.stored_events, 5)
        self.assertEqual(result.generated_commands, 2)
        self.assertEqual(result.devices["wearable_node"], "wearable-node-001")
        self.assertEqual(result.devices["connectivity_node"], "connectivity-node-001")
        self.assertEqual([row["event_type"] for row in rows], ["board_hello", "board_hello", "motion_event", "command_sent", "command_sent"])
        self.assertEqual(rows[2]["role"], "wearable_node")
        self.assertEqual(rows[2]["bridge_source"], "wearable_live")
        self.assertEqual(rows[3]["target_device_id"], "wearable-node-001")
        self.assertEqual(rows[3]["cmd"], "ask_user")
        self.assertEqual(rows[3]["command_payload"]["options"], ["safe", "help"])
        self.assertEqual(rows[4]["target_device_id"], "connectivity-node-001")
        self.assertEqual(rows[4]["cmd"], "request_location")

    def test_command_event_renders_board_downlink_message(self) -> None:
        state = board_bridge.BridgeState()
        command = board_bridge.build_command_event(
            state,
            source_event={
                "device_id": "wearable-node-001",
                "event_type": "motion_event",
                "seq": 77,
                "received_at": "2026-06-24T10:11:12+00:00",
            },
            target_role="wearable_node",
            target_device_id="wearable-node-001",
            cmd="ask_user",
            payload={"text": "Impact detected. Are you safe?", "options": ["safe", "help"]},
        )
        rendered = board_bridge.build_downlink_message(command, session_id="unit-session")

        self.assertEqual(rendered["protocol_version"], "0.2")
        self.assertEqual(rendered["source"], "pc-bridge")
        self.assertEqual(rendered["target"], "wearable-node-001")
        self.assertEqual(rendered["type"], "ask_user")
        self.assertEqual(rendered["cmd"], "ask_user")
        self.assertEqual(rendered["cmd_id"], "bridge-cmd-000001")
        self.assertEqual(rendered["seq"], 1)
        self.assertEqual(rendered["timestamp_ms"], 1782295872000)
        self.assertEqual(rendered["session_id"], "unit-session")
        self.assertEqual(rendered["payload"]["options"], ["safe", "help"])

    def test_uplink_confirmation_preserves_demo_correlation_fields(self) -> None:
        state = board_bridge.BridgeState()
        event = board_bridge.normalize_message(
            {
                "type": "user_confirmation",
                "device_id": "wearable-node-001",
                "role": "wearable_node",
                "seq": 5,
                "device_monotonic_ms": 71522,
                "source": "amoled_touch_demo",
                "response": "safe",
                "cmd_id": "demo-v0-2-123",
                "session_id": "demo-live",
            },
            received_at="2026-06-25T08:00:00+00:00",
            bridge_source="amoled_live",
            state=state,
        )

        self.assertEqual(event["event_type"], "user_confirmation")
        self.assertEqual(event["response"], "safe")
        self.assertEqual(event["cmd_id"], "demo-v0-2-123")
        self.assertEqual(event["session_id"], "demo-live")
        self.assertEqual(event["source"], "amoled_touch_demo")

    def test_bridge_motion_event_records_as_unverified_imu_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_log = Path(tmp) / "events.jsonl"
            board_bridge.consume_named_sources(
                {
                    "boot": [
                        j({"type": "hello", "device_id": "wearable-node-001", "role": "wearable_node"}),
                        j({"type": "hello", "device_id": "connectivity-node-001", "role": "connectivity_node"}),
                    ],
                    "wearable": [
                        j(
                            {
                                "device_id": "wearable-node-001",
                                "type": "motion_event",
                                "seq": 7,
                                "device_monotonic_ms": 1200,
                                "sensor_model": "QMI8658",
                                "sample_hz": 50,
                                "payload": {
                                    "impact_score": 0.91,
                                    "fall_score": 0.77,
                                    "accel_mg": [12, -8, 1004],
                                    "gyro_mdps": [10, 20, -30],
                                },
                            }
                        )
                    ],
                },
                event_log,
                now=lambda: "2026-06-23T10:00:00+00:00",
            )
            rows = read_jsonl(event_log)
            recording = session_recorder.build_recording(
                rows,
                event_log=event_log,
                session_id="dual-board-bridge-test",
                created_at="2026-06-23T10:01:00+00:00",
            )
            output_dir = Path(tmp) / "recording"
            session_recorder.write_recording(recording, output_dir)
            report = session_inspector.inspect_recording(output_dir)

        frames = recording["sensor_frames"]
        imu_frames = [frame for frame in frames if frame["frame_type"] == "imu_motion"]
        self.assertEqual(len(imu_frames), 1)
        self.assertEqual(imu_frames[0]["source_availability"], "bridge_uplink")
        self.assertEqual(imu_frames[0]["source_status"], "unverified")
        self.assertEqual(imu_frames[0]["sensor_model"], "QMI8658")
        self.assertEqual(imu_frames[0]["sample_hz"], 50)
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["frame_types"]["imu_motion"], 1)

    def test_cli_consumes_file_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "boot.jsonl"
            live = root / "live.jsonl"
            event_log = root / "events.jsonl"
            boot.write_text(
                "\n".join(
                    [
                        j({"type": "hello", "device_id": "wearable-node-001", "role": "wearable_node"}),
                        j({"type": "hello", "device_id": "connectivity-node-001", "role": "connectivity_node"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            live.write_text(
                j(
                    {
                        "source": "wearable-node-001",
                        "type": "motion_event",
                        "seq": 9,
                        "payload": {"impact_score": 0.2, "fall_score": 0.1},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()) as output:
                exit_code = board_bridge_cli.main(
                    [
                        "--source",
                        f"boot={boot}",
                        "--source",
                        f"wearable={live}",
                        "--event-log",
                        str(event_log),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            rows = read_jsonl(event_log)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["stored_events"], 3)
        self.assertEqual(payload["generated_commands"], 0)
        self.assertEqual(rows[-1]["event_type"], "motion_event")

    def test_cli_consumes_windows_utf8_bom_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "boot.jsonl"
            event_log = root / "events.jsonl"
            boot.write_text(
                j({"type": "hello", "device_id": "wearable-node-001", "role": "wearable_node"})
                + "\n",
                encoding="utf-8-sig",
            )

            with redirect_stdout(StringIO()) as output:
                exit_code = board_bridge_cli.main(
                    [
                        "--source",
                        f"boot={boot}",
                        "--event-log",
                        str(event_log),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            rows = read_jsonl(event_log)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["stored_events"], 1)
        self.assertEqual(payload["skipped_lines"], 0)
        self.assertEqual(rows[0]["event_type"], "board_hello")


if __name__ == "__main__":
    unittest.main()
