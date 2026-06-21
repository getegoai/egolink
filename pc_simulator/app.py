"""Minimal Ego Link P0 PC Simulator dashboard.

This is intentionally dependency-free so the first demo can run on a clean
Python install:

    python pc_simulator/app.py --port 8787
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pc_simulator import event_store, protocol, safety_companion


DEVICE_ID = protocol.DEVICE_ID
RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
EVENT_LOG = RUNTIME_DIR / "events.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeviceState:
    device_id: str = DEVICE_ID
    online: bool = True
    seq: int = 0
    battery: int = 87
    guard_mode: str = "child_safety"
    link_type: str = "mock_4g_over_wifi"
    rssi: int = -61
    modem_state: str = "mock_data_ready"
    gnss_state: str = "mock_fix"
    lat: float = 22.543096
    lon: float = 114.057865
    queue_size: int = 0
    last_seen_at: str = ""
    last_seen_source: str = "simulator"
    last_command: str = ""


STATE = DeviceState(last_seen_at=utc_now())
EVENTS: list[dict[str, Any]] = []


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), SimulatorHandler)
    print(f"Ego Link PC Simulator running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ego Link P0 PC Simulator.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    return parser.parse_args(argv)


class SimulatorHandler(BaseHTTPRequestHandler):
    server_version = "EgoLinkP0Simulator/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.respond_html(render_dashboard())
            return
        if path == "/api/state":
            self.respond_json(snapshot())
            return
        self.respond_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/mock/heartbeat":
            event = heartbeat()
            self.respond_json({"ok": True, "event": event, "state": snapshot()})
            return
        if path == "/api/mock/location":
            event = location_report()
            self.respond_json({"ok": True, "event": event, "state": snapshot()})
            return
        if path == "/api/mock/sos":
            event = sos_pressed()
            self.respond_json({"ok": True, "event": event, "state": snapshot()})
            return
        if path == "/api/mock/wake":
            event = wake_detected()
            self.respond_json({"ok": True, "event": event, "state": snapshot()})
            return
        if path == "/api/cmd/play_prompt":
            event = command_sent("play_prompt", "你已经离开安全区域，请确认是否需要联系家长。")
            self.respond_json({"ok": True, "event": event, "state": snapshot()})
            return
        if path == "/api/safety/evaluate":
            try:
                result = safety_companion.evaluate_request(self.read_json_body())
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.respond_json(
                    {
                        "ok": False,
                        "error": "invalid_safety_evaluation_request",
                        "detail": safety_companion.error_message(error),
                    },
                    status=400,
                )
                return
            self.respond_json({"ok": True, **result})
            return
        if path == "/api/safety/replay":
            try:
                replay = safety_companion.replay_scenarios(self.read_optional_json_body().get("scenario_ids"))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.respond_json(
                    {
                        "ok": False,
                        "error": "invalid_safety_replay_request",
                        "detail": safety_companion.error_message(error),
                    },
                    status=400,
                )
                return
            persisted = persist_safety_replay(replay)
            self.respond_json({"ok": True, **replay, "persisted_events": persisted, "state": snapshot()})
            return
        if path == "/api/safety/process-events":
            try:
                body = self.read_optional_json_body()
                limit = int(body.get("limit", 20))
                result = process_safety_events(limit=limit)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.respond_json(
                    {
                        "ok": False,
                        "error": "invalid_safety_process_request",
                        "detail": safety_companion.error_message(error),
                    },
                    status=400,
                )
                return
            self.respond_json({"ok": True, **result, "state": snapshot()})
            return
        self.respond_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def respond_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            raise ValueError("request body is empty")
        if length > 1_000_000:
            raise ValueError("request body is too large")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def read_optional_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("request body is too large")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value


def heartbeat() -> dict[str, Any]:
    return append_event(
        "heartbeat",
        {
            "fw_version": "0.1.0-sim",
            "hw_target": "waveshare_esp32s3_sim7670g_4g",
            "battery": STATE.battery,
            "charging": False,
            "link_type": STATE.link_type,
            "rssi": -61,
            "modem_state": STATE.modem_state,
            "gnss_state": STATE.gnss_state,
            "guard_mode": STATE.guard_mode,
            "queue_size": STATE.queue_size,
        },
    )


def location_report() -> dict[str, Any]:
    STATE.lat += 0.00008
    STATE.lon += 0.00006
    return append_event(
        "location_report",
        {
            "priority": "normal",
            "source": "mock_gnss",
            "lat": round(STATE.lat, 6),
            "lon": round(STATE.lon, 6),
            "speed_mps": 1.2,
            "accuracy_m": 8.5,
            "battery": STATE.battery,
        },
    )


def sos_pressed() -> dict[str, Any]:
    return append_event(
        "sos_pressed",
        {
            "priority": "critical",
            "source": "dashboard_button",
            "lat": round(STATE.lat, 6),
            "lon": round(STATE.lon, 6),
            "accuracy_m": 8.5,
            "battery": STATE.battery,
        },
    )


def wake_detected() -> dict[str, Any]:
    return append_event(
        "wake_detected",
        {
            "priority": "normal",
            "source": "mock_wake",
            "keyword": "小E",
            "confidence": 0.92,
            "battery": STATE.battery,
        },
    )


def command_sent(
    command: str,
    text: str,
    *,
    command_id: str | None = None,
    safety_class: str | None = None,
    base_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    STATE.last_command = command
    payload: dict[str, Any] = {
        "priority": "normal",
        "direction": "downlink",
        "cmd": command,
        "text": text,
        "level": "warning",
        "expire_sec": 60,
    }
    if command_id is not None:
        payload["command_id"] = command_id
    if safety_class is not None:
        payload["safety_class"] = safety_class
    if base_command is not None:
        payload["base_command"] = base_command
    return append_event(
        "command_sent",
        payload,
    )


def append_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    STATE.seq += 1
    STATE.last_seen_at = utc_now()
    priority = str(payload.pop("priority", "normal"))
    if event_type == "heartbeat":
        event = protocol.status_message(STATE.device_id, STATE.last_seen_at, STATE.seq, **payload)
    elif event_type == "command_sent":
        command_name = str(payload.pop("cmd", "unknown"))
        event = protocol.command_message(f"cmd-{STATE.seq:04d}", command_name, **payload)
        event["device_id"] = STATE.device_id
        event["ts"] = STATE.last_seen_at
        event["seq"] = STATE.seq
        event["event_type"] = event_type
        event["priority"] = priority
    else:
        event = protocol.event_message(STATE.device_id, STATE.last_seen_at, STATE.seq, event_type, priority, **payload)
    EVENTS.insert(0, event)
    del EVENTS[40:]
    write_event(event)
    return event


def write_event(event: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    event_store.append_jsonl(EVENT_LOG, event)


def persist_safety_replay(replay: dict[str, Any]) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for record in replay["records"]:
        safety_event = record.get("safety_event")
        if safety_event is not None:
            output = record["model_output"]
            persisted.append(
                append_event(
                    "safety_event",
                    {
                        "priority": output["priority"],
                        "source": "safety_replay",
                        "scenario_id": record["scenario_id"],
                        "risk_type": output["risk_type"],
                        "risk_score": output["risk_score"],
                        "confidence": output["confidence"],
                        "recommended_action": output["recommended_action"],
                        "evidence_request": output["evidence_request"],
                        "privacy_mode": safety_event["privacy"]["privacy_mode"],
                        "raw_evidence_allowed": safety_event["privacy"]["raw_evidence_allowed"],
                        "safety_event": safety_event,
                    },
                )
            )
        base_command = record.get("base_command")
        if base_command is not None:
            persisted.append(
                command_sent(
                    str(base_command["command"]),
                    safety_command_text(base_command),
                    command_id=str(base_command["command_id"]),
                    safety_class=str(base_command["safety_class"]),
                    base_command=base_command,
                )
            )
    return persisted


def process_safety_events(*, limit: int = 20) -> dict[str, Any]:
    events = recent_events(limit=limit)
    device = device_snapshot(events)
    processed_keys = processed_safety_source_keys(events)
    records: list[dict[str, Any]] = []
    persisted: list[dict[str, Any]] = []

    for event in sorted(events, key=event_time):
        if not safety_companion.is_evaluable_event(event):
            continue
        source_key = safety_companion.source_event_key(event)
        if source_key in processed_keys:
            continue
        bundle = safety_companion.evaluate_event(event, device)
        records.append(bundle)
        persisted.extend(persist_safety_bundle(bundle))
        processed_keys.add(source_key)

    return {
        "processed": len(records),
        "records": records,
        "persisted_events": persisted,
        "summary": {
            "safety_evaluations": sum(1 for item in persisted if item.get("event_type") == "safety_evaluation"),
            "safety_events": sum(1 for item in persisted if item.get("event_type") == "safety_event"),
            "base_commands": sum(1 for item in persisted if item.get("event_type") == "command_sent"),
        },
    }


def processed_safety_source_keys(events: list[dict[str, Any]]) -> set[str]:
    return {
        str(event.get("source_event_key"))
        for event in events
        if event.get("event_type") in {"safety_evaluation", "safety_event"} and event.get("source_event_key")
    }


def persist_safety_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    output = bundle["model_output"]
    source_key = str(bundle.get("source_event_key") or "")
    source_type = str(bundle.get("source_event_type") or "")
    persisted.append(
        append_event(
            "safety_evaluation",
            {
                "priority": output["priority"],
                "source": "safety_flow",
                "source_event_key": source_key,
                "source_event_type": source_type,
                "risk_type": output["risk_type"],
                "risk_score": output["risk_score"],
                "confidence": output["confidence"],
                "recommended_action": output["recommended_action"],
                "evidence_request": output["evidence_request"],
                "model_output": output,
            },
        )
    )

    safety_event = bundle.get("safety_event")
    if safety_event is not None:
        persisted.append(
            append_event(
                "safety_event",
                {
                    "priority": output["priority"],
                    "source": "safety_flow",
                    "source_event_key": source_key,
                    "source_event_type": source_type,
                    "risk_type": output["risk_type"],
                    "risk_score": output["risk_score"],
                    "confidence": output["confidence"],
                    "recommended_action": output["recommended_action"],
                    "evidence_request": output["evidence_request"],
                    "privacy_mode": safety_event["privacy"]["privacy_mode"],
                    "raw_evidence_allowed": safety_event["privacy"]["raw_evidence_allowed"],
                    "safety_event": safety_event,
                },
            )
        )

    base_command = bundle.get("base_command")
    if base_command is not None:
        persisted.append(
            command_sent(
                str(base_command["command"]),
                safety_command_text(base_command),
                command_id=str(base_command["command_id"]),
                safety_class=str(base_command["safety_class"]),
                base_command=base_command,
            )
        )
    return persisted


def safety_command_text(command: dict[str, Any]) -> str:
    args = command.get("args", {})
    risk_type = args.get("risk_type", "unknown")
    if args.get("recommended_action") == "urgent_escalation":
        return f"SIMULATED urgent check-in for {risk_type}; no call, camera, or recording started."
    return f"SIMULATED safety check-in for {risk_type}; no external action started."


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    candidates = EVENTS[:] + event_store.load_recent(EVENT_LOG, limit=limit * 2)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in candidates:
        key = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(event)
    merged.sort(key=event_time, reverse=True)
    return merged[:limit]


def event_time(event: dict[str, Any]) -> str:
    return str(event.get("received_at") or event.get("ts") or "")


def device_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    device = asdict(STATE)
    if events:
        device["last_seen_at"] = ""
        device["last_seen_source"] = "simulator"
    latest_status = next((event for event in events if event.get("message_type") == "status"), None)
    latest_location = next((event for event in events if event.get("event_type") == "location_report"), None)
    if latest_status is not None:
        apply_status_event(device, latest_status)
    if latest_location is not None:
        apply_location_event(device, latest_location)
    return device


def apply_status_event(device: dict[str, Any], event: dict[str, Any]) -> None:
    if "seq" in event:
        try:
            device["seq"] = max(int(device.get("seq", 0)), int(event["seq"]))
        except (TypeError, ValueError):
            device["seq"] = event["seq"]
    for field in [
        "device_id",
        "battery",
        "guard_mode",
        "link_type",
        "rssi",
        "modem_state",
        "gnss_state",
        "queue_size",
    ]:
        if field in event:
            device[field] = event[field]
    device["online"] = True
    device["last_seen_at"] = event_time(event)
    device["last_seen_source"] = event_source_label(event)


def apply_location_event(device: dict[str, Any], event: dict[str, Any]) -> None:
    for field in ["lat", "lon", "gnss_state"]:
        if field in event and event[field] not in (None, ""):
            device[field] = event[field]
    device["online"] = True
    if event_time(event) >= str(device.get("last_seen_at") or ""):
        device["last_seen_at"] = event_time(event)
        device["last_seen_source"] = event_source_label(event)


def event_source_label(event: dict[str, Any]) -> str:
    if event.get("ingest_source"):
        return "mqtt"
    source = str(event.get("source") or "")
    return source if source else "simulator"


def snapshot() -> dict[str, Any]:
    events = recent_events(limit=20)
    device = device_snapshot(events)
    return {
        "device": device,
        "events": events,
        "safety_companion": safety_companion.evaluate(events, device),
    }


def render_dashboard() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ego Link P0 Simulator</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d8dde6;
      --text: #17202a;
      --muted: #667085;
      --accent: #0f766e;
      --danger: #c2410c;
      --warn: #b45309;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 18px 22px 10px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 360px) 1fr;
      gap: 16px;
      padding: 16px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    h2 { margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }
    .metric {
      display: grid;
      grid-template-columns: 128px 1fr;
      gap: 8px;
      padding: 7px 0;
      border-bottom: 1px solid #edf0f5;
      font-size: 14px;
    }
    .metric span:first-child { color: var(--muted); }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      font-weight: 600;
      color: var(--accent);
    }
    .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--accent);
    }
    .actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    button {
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      font-size: 14px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); }
    button.danger {
      border-color: #fed7aa;
      color: var(--danger);
      font-weight: 600;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      padding: 9px 8px;
      border-bottom: 1px solid #edf0f5;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    .critical { color: var(--danger); font-weight: 700; }
    .normal { color: var(--accent); }
    .downlink { color: var(--warn); }
    @media (max-width: 760px) {
      main { grid-template-columns: 1fr; }
      .actions { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Ego Link P0 Simulator</h1>
  </header>
  <main>
    <div>
      <section>
        <h2>Device</h2>
        <div class="metric"><span>Status</span><span class="status"><i class="dot"></i><b id="online">Online</b></span></div>
        <div class="metric"><span>Device ID</span><span id="device_id"></span></div>
        <div class="metric"><span>Seq</span><span id="seq"></span></div>
        <div class="metric"><span>Battery</span><span id="battery"></span></div>
        <div class="metric"><span>Mode</span><span id="guard_mode"></span></div>
        <div class="metric"><span>Link</span><span id="link_type"></span></div>
        <div class="metric"><span>RSSI</span><span id="rssi"></span></div>
        <div class="metric"><span>Position</span><span id="position"></span></div>
        <div class="metric"><span>Queue</span><span id="queue_size"></span></div>
        <div class="metric"><span>Last Seen</span><span id="last_seen_at"></span></div>
        <div class="metric"><span>Source</span><span id="last_seen_source"></span></div>
        <div class="metric"><span>Last Command</span><span id="last_command"></span></div>
      </section>
      <section style="margin-top: 16px;">
        <h2>Safety</h2>
        <div class="metric"><span>Risk</span><span id="safety_risk"></span></div>
        <div class="metric"><span>Score</span><span id="safety_score"></span></div>
        <div class="metric"><span>Action</span><span id="safety_action"></span></div>
        <div class="metric"><span>Reasons</span><span id="safety_reasons"></span></div>
      </section>
      <section style="margin-top: 16px;">
        <h2>Actions</h2>
        <div class="actions">
          <button onclick="post('/api/mock/heartbeat')">Heartbeat</button>
          <button onclick="post('/api/mock/location')">Location</button>
          <button onclick="post('/api/mock/wake')">Wake</button>
          <button class="danger" onclick="post('/api/mock/sos')">SOS</button>
          <button onclick="post('/api/cmd/play_prompt')">Play Prompt</button>
        </div>
      </section>
    </div>
    <section>
      <h2>Recent Events</h2>
      <table>
        <thead><tr><th>Seq</th><th>Type</th><th>Priority</th><th>Detail</th><th>Time</th></tr></thead>
        <tbody id="events"></tbody>
      </table>
    </section>
  </main>
  <script>
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[ch]));
    }
    function eventDetail(e) {
      if (e.event_type === 'sensor_sample') {
        const parts = [];
        if (e.sensor_kind) parts.push(e.sensor_kind);
        if (e.wifi_rssi !== undefined) parts.push('RSSI ' + e.wifi_rssi);
        if (e.free_heap_bytes !== undefined) parts.push('heap ' + e.free_heap_bytes);
        return parts.join(' / ');
      }
      if (e.event_type === 'location_report') {
        const parts = [];
        if (e.fix === false) parts.push('GNSS no fix');
        if (e.lat !== undefined && e.lon !== undefined) parts.push(Number(e.lat).toFixed(6) + ', ' + Number(e.lon).toFixed(6));
        if (e.satellites !== undefined) parts.push('SV ' + e.satellites);
        if (e.source) parts.push(e.source);
        return parts.join(' / ');
      }
      if (e.event_type === 'safety_event') {
        const parts = [];
        if (e.scenario_id) parts.push(e.scenario_id);
        if (e.risk_type) parts.push('risk ' + e.risk_type);
        if (e.recommended_action) parts.push('action ' + e.recommended_action);
        if (e.evidence_request?.length) parts.push('evidence ' + e.evidence_request.join(','));
        if (e.privacy_mode) parts.push('privacy mode');
        return parts.join(' / ');
      }
      if (e.event_type === 'safety_evaluation') {
        const parts = [];
        if (e.source_event_type) parts.push('from ' + e.source_event_type);
        if (e.risk_type) parts.push('risk ' + e.risk_type);
        if (e.recommended_action) parts.push('action ' + e.recommended_action);
        return parts.join(' / ');
      }
      return e.text || e.keyword || e.cmd_id || e.status || e.source || e.hw_target || e.mqtt_topic || '';
    }
    async function post(path) {
      await fetch(path, { method: 'POST' });
      await refresh();
    }
    async function refresh() {
      const data = await fetch('/api/state').then(r => r.json());
      const d = data.device;
      device_id.textContent = d.device_id;
      online.textContent = d.online ? 'Online' : 'Offline';
      seq.textContent = d.seq;
      battery.textContent = d.battery + '%';
      guard_mode.textContent = d.guard_mode;
      link_type.textContent = d.link_type;
      rssi.textContent = d.rssi;
      position.textContent = Number(d.lat).toFixed(6) + ', ' + Number(d.lon).toFixed(6);
      queue_size.textContent = d.queue_size;
      last_seen_at.textContent = d.last_seen_at || 'none';
      last_seen_source.textContent = d.last_seen_source || 'simulator';
      last_command.textContent = d.last_command || 'none';
      const safety = data.safety_companion?.model_output || {};
      safety_risk.textContent = safety.risk_type || 'none';
      safety_score.textContent = safety.risk_score !== undefined ? Number(safety.risk_score).toFixed(2) : '0.00';
      safety_action.textContent = safety.recommended_action || 'ignore';
      safety_reasons.textContent = (safety.reason_codes || []).join(', ') || 'none';
      events.innerHTML = data.events.map(e => {
        const priority = e.priority || (e.event_type === 'command_sent' ? 'downlink' : 'normal');
        const detail = eventDetail(e);
        const time = e.received_at || e.ts || '';
        return `<tr>
          <td>${escapeHtml(e.seq)}</td>
          <td>${escapeHtml(e.event_type || e.message_type || '')}</td>
          <td class="${escapeHtml(priority)}">${escapeHtml(priority)}</td>
          <td>${escapeHtml(detail)}</td>
          <td>${escapeHtml(time)}</td>
        </tr>`;
      }).join('');
    }
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())
