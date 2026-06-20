"""MQTT ingester for the Ego Link P0 PC Simulator.

The worker intentionally shells out to the Mosquitto CLI that is already used
by the project, so Stage 0 does not need an extra Python MQTT dependency.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import event_store, protocol


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1883
DEFAULT_TOPICS = ["ego/link/+/status", "ego/link/+/event", "ego/link/+/ack"]
RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
DEFAULT_EVENT_LOG = RUNTIME_DIR / "events.jsonl"
WINDOWS_MOSQUITTO_SUB = Path("C:/Program Files/mosquitto/mosquitto_sub.exe")


class MqttWorkerError(ValueError):
    """Raised when an MQTT line or payload cannot be ingested."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_mosquitto_sub(executable: str | None = None) -> str:
    if executable:
        return executable
    found = shutil.which("mosquitto_sub")
    if found:
        return found
    if WINDOWS_MOSQUITTO_SUB.exists():
        return str(WINDOWS_MOSQUITTO_SUB)
    return "mosquitto_sub"


def build_subscribe_command(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    topics: list[str] | None = None,
    executable: str | None = None,
    max_messages: int | None = None,
    wait_seconds: int | None = None,
) -> list[str]:
    command = [
        resolve_mosquitto_sub(executable),
        "-h",
        host,
        "-p",
        str(port),
        "-v",
    ]
    for topic in topics or DEFAULT_TOPICS:
        command.extend(["-t", topic])
    if max_messages is not None:
        command.extend(["-C", str(max_messages)])
    if wait_seconds is not None:
        command.extend(["-W", str(wait_seconds)])
    return command


def parse_verbose_line(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if not stripped:
        raise MqttWorkerError("empty MQTT line")
    topic, separator, payload = stripped.partition(" ")
    if not separator or not topic or not payload:
        raise MqttWorkerError("expected mosquitto_sub -v output: '<topic> <payload>'")
    return topic, payload


def event_from_payload(topic: str, payload: str, *, received_at: str | None = None) -> dict[str, Any]:
    try:
        message = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MqttWorkerError(f"invalid JSON payload: {exc.msg}") from exc

    if not isinstance(message, dict):
        raise MqttWorkerError("MQTT payload must be a JSON object")
    message_type = str(message.get("message_type", ""))
    try:
        if message_type == "status":
            event = status_event_from_message(message)
        elif message_type == "event":
            event = telemetry_event_from_message(message)
        elif message_type == "ack":
            event = ack_event_from_message(message)
        else:
            raise MqttWorkerError(f"unsupported message_type: {message_type or '<missing>'}")
    except ValueError as exc:
        raise MqttWorkerError(str(exc)) from exc

    event["mqtt_topic"] = topic
    event["ingest_source"] = "pc_simulator.mqtt_worker"
    event["received_at"] = received_at or utc_now()
    return event


def status_event_from_message(message: dict[str, Any]) -> dict[str, Any]:
    event = dict(message)
    event.setdefault("protocol_version", protocol.PROTOCOL_VERSION)
    protocol.require_fields(
        event,
        [
            "protocol_version",
            "device_id",
            "ts",
            "seq",
            "message_type",
            "battery",
            "link_type",
            "guard_mode",
            "queue_size",
        ],
    )
    event["event_type"] = "mqtt_status"
    return event


def telemetry_event_from_message(message: dict[str, Any]) -> dict[str, Any]:
    event = dict(message)
    event.setdefault("protocol_version", protocol.PROTOCOL_VERSION)
    protocol.require_fields(
        event,
        [
            "protocol_version",
            "device_id",
            "ts",
            "seq",
            "message_type",
            "event_type",
            "priority",
        ],
    )
    event.setdefault("direction", "uplink")
    return event


def ack_event_from_message(message: dict[str, Any]) -> dict[str, Any]:
    event = dict(message)
    event.setdefault("protocol_version", protocol.PROTOCOL_VERSION)
    protocol.require_fields(
        event,
        [
            "protocol_version",
            "device_id",
            "ts",
            "seq",
            "message_type",
            "cmd_id",
            "status",
        ],
    )
    event["event_type"] = "mqtt_ack"
    event.setdefault("priority", "normal")
    event.setdefault("direction", "uplink")
    return event


def status_event_from_payload(topic: str, payload: str, *, received_at: str | None = None) -> dict[str, Any]:
    event = event_from_payload(topic, payload, received_at=received_at)
    if event.get("message_type") != "status":
        raise MqttWorkerError("payload is not a status message")
    return event


def consume_lines(
    lines: Iterable[str],
    event_log: Path = DEFAULT_EVENT_LOG,
    *,
    now: Callable[[], str] = utc_now,
    errors: TextIO | None = None,
) -> int:
    stored = 0
    for line in lines:
        try:
            topic, payload = parse_verbose_line(line)
            event = event_from_payload(topic, payload, received_at=now())
        except MqttWorkerError as exc:
            if errors is not None:
                print(f"mqtt_worker skipped line: {exc}", file=errors)
            continue
        event_store.append_jsonl(event_log, event)
        stored += 1
    return stored


def run_worker(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    topics: list[str] | None = None,
    event_log: Path = DEFAULT_EVENT_LOG,
    executable: str | None = None,
    max_messages: int | None = None,
    wait_seconds: int | None = None,
) -> int:
    command = build_subscribe_command(
        host=host,
        port=port,
        topics=topics,
        executable=executable,
        max_messages=max_messages,
        wait_seconds=wait_seconds,
    )
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        if process.stdout is None:
            raise RuntimeError("mosquitto_sub stdout was not captured")
        stored = consume_lines(process.stdout, event_log, errors=sys.stderr)
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        raise
    finally:
        if process.poll() is None:
            process.terminate()

    if return_code != 0:
        raise RuntimeError(f"mosquitto_sub exited with code {return_code}")
    return stored


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Ego Link MQTT messages into the PC Simulator event log.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--topic",
        action="append",
        dest="topics",
        help="MQTT topic filter to subscribe. May be repeated. Defaults to status/event/ack.",
    )
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--mosquitto-sub", default=None, help="Path to mosquitto_sub. Defaults to PATH or Windows install path.")
    parser.add_argument("--max-messages", type=int, default=None, help="Exit after this many received MQTT messages.")
    parser.add_argument("--wait-seconds", type=int, default=None, help="Pass a receive timeout to mosquitto_sub.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    topics = args.topics or DEFAULT_TOPICS
    print(f"Listening mqtt://{args.host}:{args.port} {', '.join(topics)}")
    print(f"Writing events to {args.event_log}")
    try:
        stored = run_worker(
            host=args.host,
            port=args.port,
            topics=topics,
            event_log=args.event_log,
            executable=args.mosquitto_sub,
            max_messages=args.max_messages,
            wait_seconds=args.wait_seconds,
        )
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"mqtt_worker failed: {exc}", file=sys.stderr)
        return 1
    print(f"Stored {stored} MQTT event(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
