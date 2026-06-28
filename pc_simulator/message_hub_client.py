"""PC Simulator client for the HTTP Message Hub R0 loop."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib import error, request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import protocol


DEFAULT_HUB_URL = "http://127.0.0.1:8790"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageHubClientError(RuntimeError):
    pass


@dataclass
class SimulatedDevice:
    device_id: str = protocol.DEVICE_ID
    fw_version: str = "0.1.0-sim"
    battery: int = 87
    link_type: str = "mock_4g_over_wifi"
    guard_mode: str = "child_safety"
    queue_size: int = 0
    lat: float = 22.543096
    lon: float = 114.057865
    seq: int = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def heartbeat(self) -> dict[str, Any]:
        return protocol.status_message(
            self.device_id,
            utc_now(),
            self.next_seq(),
            fw_version=self.fw_version,
            battery=self.battery,
            charging=False,
            link_type=self.link_type,
            rssi=-61,
            modem_state="mock_data_ready",
            gnss_state="mock_fix",
            guard_mode=self.guard_mode,
            queue_size=self.queue_size,
        )

    def location_report(self) -> dict[str, Any]:
        self.lat += 0.00008
        self.lon += 0.00006
        return protocol.event_message(
            self.device_id,
            utc_now(),
            self.next_seq(),
            "location_report",
            "normal",
            fw_version=self.fw_version,
            source="mock_gnss",
            source_status="mock",
            lat=round(self.lat, 6),
            lon=round(self.lon, 6),
            speed_mps=1.2,
            accuracy_m=8.5,
            battery=self.battery,
        )

    def location_observation(self) -> dict[str, Any]:
        return protocol.event_message(
            self.device_id,
            utc_now(),
            self.next_seq(),
            "location_observation",
            "normal",
            fw_version=self.fw_version,
            source="pc_simulator_location_observation",
            source_status="mock",
            transport={"type": self.link_type, "rtt_ms": 48, "last_error": None},
            gnss={
                "enabled": True,
                "fix": True,
                "lat": round(self.lat, 6),
                "lon": round(self.lon, 6),
                "hdop": 0.9,
                "satellites": 12,
                "attempt_ms": 18000,
                "result": "fix",
            },
            cell={
                "rat": "LTE",
                "operator": "mock_operator",
                "mcc": "460",
                "mnc": "01",
                "tac": "0x230A",
                "cell_id": "mock-cell-001",
                "rsrp": -67,
                "rsrq": -21,
                "rssi": -67,
                "sinr": 19,
            },
            wifi={
                "scan_enabled": True,
                "aps": [
                    {"bssid_hash": "mock_hash_home_1", "rssi": -62},
                    {"bssid_hash": "mock_hash_home_2", "rssi": -74},
                ],
            },
            imu={"motion": "stationary", "confidence": 0.93},
            power={"battery_mv": 3920, "soc_pct": self.battery, "charging": False, "source": "mock"},
            location_belief={
                "state": "Fine",
                "lat": round(self.lat, 6),
                "lon": round(self.lon, 6),
                "radius_m": 15,
                "confidence": 0.91,
                "source": ["gnss"],
                "reason": "gnss_fix_hdop_good",
            },
        )

    def ack(self, command: dict[str, Any], status: str = "ok") -> dict[str, Any]:
        message = protocol.ack_message(self.device_id, utc_now(), self.next_seq(), str(command["cmd_id"]), status)
        message["fw_version"] = self.fw_version
        message["message"] = f"simulated ACK for {command['cmd']}"
        return message


class MessageHubClient:
    def __init__(self, base_url: str, *, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def register(self, device: SimulatedDevice) -> dict[str, Any]:
        return self.post(
            "/api/v1/devices/register",
            {"device_id": device.device_id, "fw_version": device.fw_version},
        )

    def send_heartbeat(self, device: SimulatedDevice) -> dict[str, Any]:
        return self.post(f"/api/v1/devices/{device.device_id}/heartbeat", device.heartbeat())

    def send_location(self, device: SimulatedDevice) -> dict[str, Any]:
        return self.post(f"/api/v1/devices/{device.device_id}/telemetry", device.location_report())

    def send_location_observation(self, device: SimulatedDevice) -> dict[str, Any]:
        return self.post(f"/api/v1/devices/{device.device_id}/telemetry", device.location_observation())

    def create_demo_command(self, device: SimulatedDevice, *, interval_ms: int = 5000) -> dict[str, Any]:
        return self.post(
            f"/api/v1/devices/{device.device_id}/commands",
            {"cmd": "set_report_interval", "payload": {"interval_ms": interval_ms}},
        )

    def poll_commands(self, device: SimulatedDevice) -> list[dict[str, Any]]:
        payload = self.get(f"/api/v1/devices/{device.device_id}/commands/poll")
        return list(payload.get("commands") or [])

    def ack_command(self, device: SimulatedDevice, command: dict[str, Any]) -> dict[str, Any]:
        return self.post(
            f"/api/v1/devices/{device.device_id}/commands/{command['cmd_id']}/ack",
            device.ack(command),
        )

    def get(self, path: str) -> dict[str, Any]:
        req = request.Request(self.base_url + path, headers=self.headers(), method="GET")
        return self.open(req)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self.headers()
        headers["Content-Type"] = "application/json"
        req = request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        return self.open(req)

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def open(self, req: request.Request) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MessageHubClientError(f"message hub returned HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise MessageHubClientError(f"message hub request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise MessageHubClientError("message hub response must be a JSON object")
        return payload


def run_once(
    *,
    hub_url: str = DEFAULT_HUB_URL,
    device_id: str = protocol.DEVICE_ID,
    fw_version: str = "0.1.0-sim",
    token: str | None = None,
    create_demo_command: bool = False,
) -> dict[str, Any]:
    client = MessageHubClient(hub_url, token=token)
    device = SimulatedDevice(device_id=device_id, fw_version=fw_version)
    result: dict[str, Any] = {
        "hub_url": hub_url,
        "device_id": device_id,
        "registered": client.register(device),
        "heartbeat": client.send_heartbeat(device),
        "location": client.send_location(device),
        "location_observation": client.send_location_observation(device),
    }
    if create_demo_command:
        result["created_command"] = client.create_demo_command(device)
    commands = client.poll_commands(device)
    result["polled_commands"] = commands
    result["acks"] = [client.ack_command(device, command) for command in commands]
    result["state"] = client.get("/api/state")
    result["ok"] = True
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one PC Simulator -> Message Hub R0 cycle.")
    parser.add_argument("--hub", default=DEFAULT_HUB_URL)
    parser.add_argument("--device-id", default=protocol.DEVICE_ID)
    parser.add_argument("--fw-version", default="0.1.0-sim")
    parser.add_argument("--token-env", default="EGOLINK_MESSAGE_HUB_TOKEN")
    parser.add_argument("--create-demo-command", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_once(
            hub_url=args.hub,
            device_id=args.device_id,
            fw_version=args.fw_version,
            token=os.environ.get(args.token_env) or None,
            create_demo_command=args.create_demo_command,
        )
    except MessageHubClientError as exc:
        print(f"FAIL message hub simulator: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PASS message hub simulator device={result['device_id']} hub={result['hub_url']}")
        print(f"Commands polled: {len(result['polled_commands'])}")
        print(f"ACKs sent: {len(result['acks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
