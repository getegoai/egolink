---
document_status: authoritative
last_verified: 2026-09-02
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

## Minimum Guardian Device Binding

The current code has an additive, default-off P0 authorization boundary for
the exact-location read route. When `EGOLINK_GUARDIAN_BINDINGS_FILE` names a
valid `egolink.guardian_device_bindings.v0.1` JSON file, a Guardian bearer
token may read only the devices listed for its binding. The file contains only
lowercase SHA-256 token digests; plaintext Guardian tokens must remain in the
client/secret-provisioning boundary. Device-ingest authentication remains the
separate `EGOLINK_MESSAGE_HUB_TOKEN`, and a Guardian token cannot access other
Message Hub APIs.

If the binding file is absent, the existing single-token current-state route
remains coordinate-redacted. If it is malformed, startup fails closed. A
missing/invalid Guardian token returns `401`; a valid Guardian token requesting
an unbound device returns `403` without returning location state. Query-string
flags cannot grant coordinate access. Responses remain `no-store`.

`GET /guardian-location` is the matching minimum human test surface. The page
contains no credentials or device data. It sends the entered Guardian token in
the `Authorization` header of one same-origin request, never in the URL or Web
Storage, clears the password field immediately, and renders returned values as
text. Its strict CSP permits only its same-origin script, stylesheet and API
request; it disables camera, microphone and browser geolocation. This is an
engineering acceptance surface for location belief/source, position, age,
accuracy, confidence, uncertainty, battery, SOS and stale/offline state—not a
map, polished App or product account flow.

This is a minimum local/VPS authorization seam, not complete account security:
token generation/rotation/revocation, rate limiting, client secure storage,
provisioning audit, deletion/export consent, multi-tenant administration and a
deployed penetration review remain open before sale.

`location_memory` is a P0 engineering exception, not a permanent product
ownership decision. Personal known places, common routes, GNSS-bad zones, and
long-term location memory must migrate to the device or local Ego Base by
default during productization. Server retention must be consented, minimized,
purpose-bounded, time-bounded, and deletable. See ADR-0004.

## Existing VPS Boundary

A public VPS is available for message-service deployment. GitLab is already
installed on that server and must not be modified by Ego Link message-hub tasks.
Repository files must not contain real passwords, tokens, private keys, IP
allowlists, or private device logs. Provide only `.env.example` style templates.

For Windows deployment, `scripts/deploy_message_hub_vps.ps1` normalizes the
generated remote Bash input to LF before SSH execution. Preserve that step so
carriage returns cannot become part of remote service names or paths. Prefer a
dedicated ED25519 key through `-SshKey`; never place VPS passwords or private
key contents in repository files or command arguments.

### Public Dashboard Entry

The official human-facing and target device-ingress entry is
`https://ego.example.invalid/`. Nginx terminates TLS and proxies the complete
same-origin Dashboard/API surface to the Message Hub on loopback port `8790`.
Ordinary browser HTTP redirects to HTTPS, while plaintext `/api/`, Dashboard
WebSocket, and exact AMap coordinate-conversion requests fail with `426` and
never reach the upstream. The tracked OPS-004 deployment path refuses
non-loopback Message Hub bindings.

The authorized 2026-09-05 [convergence run 001](RUNTIME_CONVERGENCE_20260905_RUN001.md)
deployed the current Location/Guardian service, loopback listener and HTTPS
virtual host, with an additional Location-only restriction keeping SOS public
routes closed. Initial TLS/authorization/plaintext-rejection checks passed;
subsequent connection timeouts left the stability window incomplete. This is
not full OPS-004 acceptance: device TLS, renewal, provider rendering and final
network stability remain unverified. The target configuration has no public
plaintext compatibility endpoint. A legacy device that cannot verify TLS
must retain its queued record and report transport unavailable; it must not
send a bearer credential or location payload over plaintext.

The reproducible virtual-host sources are:

- `scripts/ops/nginx/ego.example.invalid.bootstrap.conf` for the first ACME
  webroot challenge;
- `scripts/ops/nginx/ego.example.invalid.conf` for the final HTTPS proxy.

Certificate files and private keys remain under `/etc/letsencrypt` on the VPS
and must never be copied into the repository. Deployment, smoke, renewal, and
rollback commands are maintained in `docs/operations/VPS_RUNBOOK.md`.

### AMap Dashboard Runtime Configuration

The Dashboard's AMap JS API 2.0 application is registered under the key name
`test`. The real values are runtime configuration, not repository
documentation. This follows the
[AMap JS API security-key guide](https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode),
which recommends keeping the security code behind a server-side proxy:

- `EGOLINK_AMAP_JS_API_KEY` is the browser-visible JavaScript API key. The
  Dashboard may place it in the AMap script URL, so it is not treated as a
  server secret. Restrict it to the HTTPS production Dashboard origin
  `https://ego.example.invalid` in the AMap console and enable quota/abuse
  monitoring.
- `EGOLINK_AMAP_SECURITY_JS_CODE` is server-only. It must never appear in
  Dashboard HTML, JavaScript, public configuration APIs, logs, reports, test
  fixtures, or Git history. The Message Hub uses it only when forwarding the
  fixed same-origin `/_AMapService` path to the AMap service.

For deployment, set both values in the local process environment and run the
normal deployment script. The script accepts only its fixed runtime-variable
allowlist, rejects multiline values, and atomically upserts values that were
actually supplied. It preserves existing variables when their local value is
absent. On the VPS the values live in `/etc/egolink-message-hub.env`, owned by
root with mode `0600`, and are loaded through the existing systemd
`EnvironmentFile` boundary. Local `.env` and `.env.*` files are ignored; only
redacted `.env.example` templates may be committed.

The browser boundary is the JS API key plus a relative `/_AMapService` service
host. The security code stays behind that same-origin proxy. Missing AMap
configuration must leave the local coordinate fallback usable. SIM7670 GNSS
evidence remains WGS-84 in storage and APIs; the browser converts a copy from
`gps` to GCJ-02 with AMap's coordinate-conversion API before drawing it and
must not overwrite the source evidence.

AMap coordinate conversion and initialization use JSONP. The proxy labels a
response as `application/javascript` only for a canonical allowlisted endpoint
with exactly one bounded, syntactically valid callback and a safe upstream
media type. A request without a callback remains JSON; malformed or repeated
callbacks and unexpected HTML fail closed. Keep the
`X-Content-Type-Options: nosniff` and `Cache-Control: no-store` response headers
on coordinate responses so a future MIME regression cannot be hidden by
permissive browser sniffing or cached location data.

AMap is third-party JavaScript running in the authenticated Dashboard page.
When a verified point is rendered, AMap receives the bounded coordinates used
for conversion and viewport display. This is an explicit P0 privacy and supply-
chain boundary, not a confidentiality boundary. Do not use the provider view
for users or sessions whose location-sharing consent is absent, and move the
map into a separately isolated origin before a production privacy claim.

To rotate either value, update the matching local process environment value,
deploy and restart the Message Hub, verify the provider and fallback paths,
then revoke the old credential in the AMap console. Never record credential
values, partial values, hashes, or fingerprints in task packets or evidence.

## OPS-004 Authenticated TLS Boundary

The target firmware base origin is exactly `https://ego.example.invalid`, with an
independently configured expected host of `ego.example.invalid`. The ESP-IDF HTTP
path attaches the built-in CA bundle, keeps hostname checking enabled, disables
automatic redirects, rejects missing or malformed bearer tokens, and rejects
plaintext, unexpected authority, explicit port, userinfo, path, query, or
fragment before network and sensor startup.

Current SIMCom documentation describes CA trust, server authentication, SNI,
local-time checking and certificate common-name checking for qualifying
SIM76XX firmware. The exact SIM7670G firmware and its negative behavior remain
unverified, so the current OPS-004 firmware preflight still stops the modem AT
HTTP path before network startup or payload transmission. An `https://` string
or documented command is not peer-verification evidence. The bounded,
query-only `tls-capability` diagnostic must run first under fresh operator
authorization; provisioning and wrong-CA/hostname/time/SNI rejection require a
separate no-credential hardware test before this path can be enabled.

The only plaintext engineering fallback is a diagnostic `GET /health` with no
bearer token, body, device command, or location. It requires an explicit UTC
expiry no more than one hour in the future and is always marked
`production_acceptable=false`. It cannot satisfy an OPS-004 or product Gate.

## Transport Options

The implementation keeps a transport boundary so later MQTT-over-TLS migration
remains possible. Authenticated device ingress must use a peer-verified secure
transport; plaintext HTTP is historical engineering evidence only.

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

LOC-021 adds the versioned `egolink.location_state_envelope.v0.1` contract for
device-derived Location Engine state. Its source-event clock and boot/session/
sequence identity own ordering; the Message Hub's receive timestamp is only
transport evidence. LOC-021C adds an authenticated bounded JSON ingest route
and authenticated current-state route backed by the additive SQLite timeline.
The existing single bearer token cannot establish Guardian-device binding, so
exact coordinates remain redacted and no query parameter can unlock them. UTC
event clocks may be compared with current server UTC; boot-monotonic freshness
remains unavailable without a trustworthy mapping. Receive time substitutes
for neither source clock.

An accepted location-state POST now returns an additive
`egolink.persistent_priority_outbox.ack.v0.1` object in `delivery_ack`. The ACK
is created only after the SQLite transaction has durably accepted the envelope
or confirmed an exact idempotent duplicate. Its `payload_sha256` hashes the
exact request bytes without JSON re-encoding; the device adapter must persist
and resend those same bytes. The matching bounded outbox event ID is
`loc-<payload_sha256>`. HTTP status alone never authorizes deletion. The
response explicitly labels its scope `server_durable_ingest_only`: it does not
claim Guardian display, human acknowledgement, freshness or P0 acceptance, and
it never echoes the location state or coordinates. Device and session IDs use
the shared outbox-safe ASCII `1..128` identifier subset so the envelope and
durable queue cannot disagree at runtime.

## Minimal HTTP API

```text
POST /api/v1/devices/register
POST /api/v1/devices/{device_id}/heartbeat
POST /api/v1/devices/{device_id}/telemetry
POST /api/v1/devices/{device_id}/ack
POST /api/v1/devices/{device_id}/error
POST /api/v1/location-states
POST /api/v1/devices/{device_id}/raw-ingest
GET  /api/v1/devices/{device_id}/commands/poll
GET  /api/v1/devices/{device_id}/commands/poll.raw
POST /api/v1/devices/{device_id}/commands/{cmd_id}/ack
POST /api/v1/devices/{device_id}/commands/{cmd_id}/ack.raw

GET  /api/v1/devices
GET  /api/v1/devices/{device_id}
GET  /api/v1/devices/{device_id}/telemetry/latest
GET  /api/v1/devices/{device_id}/telemetry/history
GET  /api/v1/devices/{device_id}/location-state/current
GET  /api/v1/devices/{device_id}/raw-frames
GET  /api/v1/devices/{device_id}/field-export?started_at=...&ended_at=...
POST /api/v1/devices/{device_id}/commands
GET  /api/v1/devices/{device_id}/commands

GET  /api/v1/test-runs
POST /api/v1/test-runs
GET  /api/v1/test-runs/{test_run_id}/export
GET  /api/v1/product-demo/latest
GET  /api/v1/progress/latest

GET  /guardian-location
GET  /health
WS   /ws/dashboard
```

`field-export` is an authenticated, read-only D2 evidence route. It accepts an
ISO-8601 server-receive-time window no longer than 48 hours, returns messages,
command lifecycle records, and redacted raw-frame records for one device, and
caps each collection at 5,000 rows by default (10,000 hard maximum). Callers
must treat any `window.truncated=true` collection as incomplete evidence.

## Product Demo Review Gate

The KR-008 product-demo path uses a separate no-hardware Web review gate:

```powershell
python scripts/validate_product_demo_web_review.py --hub-url https://ego.example.invalid --review-id <review-id> --output-dir reports/product_demo_web_review/<review-id> --json
```

The gate checks Message Hub health, `/api/v1/product-demo/latest`,
`/api/state` Product Demo consistency, Dashboard Product Demo markers, and the
explicit KR-008 release boundary. It is read-only from the Message Hub
perspective: it must not send device commands, flash firmware, deploy code, or
touch GitLab. A PASS means the latest product-demo report is reviewable through
Web/API; it is not a KR-008 release claim.

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

HTTPS uses:

```text
Authorization: Bearer <device_token>
```

MQTT may use username/password or client certificates.
