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

from pc_simulator import event_store, protocol


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


def command_sent(command: str, text: str) -> dict[str, Any]:
    STATE.last_command = command
    return append_event(
        "command_sent",
        {
            "priority": "normal",
            "direction": "downlink",
            "cmd": command,
            "text": text,
            "level": "warning",
            "expire_sec": 60,
        },
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
    for event in events:
        if event.get("message_type") == "status":
            apply_status_event(device, event)
            break
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
    device["last_seen_source"] = "mqtt" if event.get("ingest_source") else "simulator"


def snapshot() -> dict[str, Any]:
    events = recent_events(limit=20)
    return {"device": device_snapshot(events), "events": events}


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
