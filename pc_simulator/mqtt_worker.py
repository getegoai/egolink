"""MQTT status ingester for the Ego Link P0 PC Simulator.

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
DEFAULT_TOPIC = "ego/link/+/status"
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
    topic: str = DEFAULT_TOPIC,
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
        "-t",
        topic,
        "-v",
    ]
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


def status_event_from_payload(topic: str, payload: str, *, received_at: str | None = None) -> dict[str, Any]:
    try:
        message = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MqttWorkerError(f"invalid JSON payload: {exc.msg}") from exc

    if not isinstance(message, dict):
        raise MqttWorkerError("MQTT payload must be a JSON object")
    if message.get("message_type") != "status":
        raise MqttWorkerError("only status messages are accepted by this worker")

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
    event["mqtt_topic"] = topic
    event["ingest_source"] = "pc_simulator.mqtt_worker"
    event["received_at"] = received_at or utc_now()
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
            event = status_event_from_payload(topic, payload, received_at=now())
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
    topic: str = DEFAULT_TOPIC,
    event_log: Path = DEFAULT_EVENT_LOG,
    executable: str | None = None,
    max_messages: int | None = None,
    wait_seconds: int | None = None,
) -> int:
    command = build_subscribe_command(
        host=host,
        port=port,
        topic=topic,
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
    parser = argparse.ArgumentParser(description="Ingest Ego Link status MQTT messages into the PC Simulator event log.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--mosquitto-sub", default=None, help="Path to mosquitto_sub. Defaults to PATH or Windows install path.")
    parser.add_argument("--max-messages", type=int, default=None, help="Exit after this many received MQTT messages.")
    parser.add_argument("--wait-seconds", type=int, default=None, help="Pass a receive timeout to mosquitto_sub.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"Listening mqtt://{args.host}:{args.port} {args.topic}")
    print(f"Writing events to {args.event_log}")
    try:
        stored = run_worker(
            host=args.host,
            port=args.port,
            topic=args.topic,
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
    print(f"Stored {stored} MQTT status event(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
