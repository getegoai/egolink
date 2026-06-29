---
document_status: authoritative
last_verified: 2026-06-27
verified_by: codex
---

# VPS Message Hub

The Public VPS Message Hub is the default P0 message center for product-like
development and field testing.

```text
Real device firmware ----\
                         -> Public VPS Message Hub -> Web Dashboard
PC Simulator ----------/          |
                                  v
                         storage, logs, command queue
```

## Responsibilities

The VPS Message Hub is responsible for:

- device registration and authentication;
- receiving heartbeat, telemetry, GNSS, network, power, error, and log summary
  messages;
- preserving raw device frames before parser or schema conversion when a raw
  transport profile is used;
- storing the minimum P0 engineering evidence needed for replayable tests;
- exposing device state, latest location, history, command status, and event
  logs to the Web Dashboard;
- keeping downlink commands and tracking ACK, timeout, and failure state;
- exporting field-test reports.

The VPS Message Hub is not responsible for:

- becoming Ego Base or the core local AI agent;
- storing long-term private context, memory, raw audio, raw images, or screen
  content by default;
- calling a cloud LLM as the core safety path;
- treating USB serial logs as formal runtime evidence.

## Existing VPS Boundary

A public VPS is available for message-service deployment. GitLab is already
installed on that server and must not be modified by Ego Link message-hub tasks.
Repository files must not contain real passwords, tokens, private keys, IP
allowlists, or private device logs. Provide only `.env.example` style templates.

## Transport Options

P0 may start with either HTTP polling or MQTT, but the implementation must keep
a transport boundary so later migration is possible.

Recommended shape:

- device uplink: MQTT over TLS or HTTPS POST;
- device downlink: MQTT subscribe or HTTPS command polling;
- Web Dashboard: HTTPS plus WebSocket or server-sent refresh;
- storage: SQLite for P0, PostgreSQL only when multi-device or long-term runs
  justify it;
- deployment: systemd or Docker Compose;
- public entry: prefer 443 for HTTPS; use 8883 for MQTT over TLS if needed.

Development ports such as 1883, 8000, 8080, or 8787 must be documented as
development-only when exposed.

## Raw-First Ingest Boundary

For `raw-frame.p0.v1`, the Message Hub must store the received frame bytes,
byte length, hash/checksum metadata, receive timestamp, device ID, and parser
status before deriving JSON state for Web/API clients. Parser failure is an
observable result, not a reason to drop the record. This is especially
important for LTE field tests, where a partial frame, checksum mismatch, or
unsupported command payload still explains a real transport condition.

Existing `egolink.p0.v1` JSON endpoints may remain for PC simulator, Web, and
legacy firmware compatibility. Raw-frame endpoints or content negotiation
should be additive.

## Minimal HTTP API

```text
POST /api/v1/devices/register
POST /api/v1/devices/{device_id}/heartbeat
POST /api/v1/devices/{device_id}/telemetry
POST /api/v1/devices/{device_id}/ack
POST /api/v1/devices/{device_id}/error
GET  /api/v1/devices/{device_id}/commands/poll
POST /api/v1/devices/{device_id}/commands/{cmd_id}/ack

GET  /api/v1/devices
GET  /api/v1/devices/{device_id}
GET  /api/v1/devices/{device_id}/telemetry/latest
GET  /api/v1/devices/{device_id}/telemetry/history
POST /api/v1/devices/{device_id}/commands
GET  /api/v1/devices/{device_id}/commands

GET  /api/v1/test-runs
POST /api/v1/test-runs
GET  /api/v1/test-runs/{test_run_id}/export

GET  /health
WS   /ws/dashboard
```

## Minimal MQTT Topics

Existing local development uses:

```text
ego/link/{device_id}/status
ego/link/{device_id}/event
ego/link/{device_id}/ack
```

The VPS implementation may preserve that shape for compatibility or add aliases
under a versioned public namespace:

```text
ego-link/v1/device/{device_id}/heartbeat
ego-link/v1/device/{device_id}/telemetry
ego-link/v1/device/{device_id}/ack
ego-link/v1/device/{device_id}/error
ego-link/v1/device/{device_id}/log
ego-link/v1/server/{device_id}/command
ego-link/v1/server/{device_id}/config
```

`PROTO-001` must decide the canonical public namespace before firmware depends
on it.

## Data Tables

At minimum, keep durable records for:

- devices;
- telemetry;
- commands;
- ACKs;
- errors;
- test runs;
- event log rows.

All server-received messages must get a server receive timestamp. Device-provided
timestamps are useful but cannot be the only ordering source.

## Authentication

P0 minimum:

- each device has a unique `device_id`;
- each device has a token or secret configured outside the repository;
- server requests authenticate the device token;
- repository examples use `.env.example` and fake values only.

HTTP may use:

```text
Authorization: Bearer <device_token>
```

MQTT may use username/password or client certificates.
