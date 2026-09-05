---
id: OPS-004
title: Migrate device ingress from plaintext HTTP to TLS
status: active
priority: critical
lane: C
execution_state: in_progress
queue_reason: offline candidate and read-only capability probe implemented; live modem probe, deployment and peer verification require separate intent
requires_hardware: false
created: 2026-08-23
last_updated: 2026-09-02

context:
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/current/ACTIVE_BUILD.md

allowed_paths:
  - docs/tasks/active/OPS-004_DEVICE_HTTPS_INGRESS.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/LTE_TRANSPORT.md
  - docs/operations/VPS_RUNBOOK.md
  - firmware/mqtt_heartbeat/main/app_main.c
  - firmware/mqtt_heartbeat/main/Kconfig.projbuild
  - firmware/mqtt_heartbeat/sdkconfig.vps_http.defaults.example
  - scripts/deploy_message_hub_vps.ps1
  - scripts/diag_lte_http_at.py
  - scripts/ops/nginx/ego.example.invalid.bootstrap.conf
  - scripts/ops/nginx/ego.example.invalid.conf
  - scripts/ops/certbot/10-egolink-nginx-reload.sh
  - tools/run_ft001b_imu_burst.py
  - quality_tests/test_mqtt_heartbeat_firmware.py
  - quality_tests/test_lte_http_at_diag.py
  - quality_tests/test_vps_https_config.py

out_of_scope:
  - deploying or rotating production credentials without operator intent
  - hiding a compatibility fallback or accepting invalid certificates
  - claiming persistent Store-and-Forward
---

# Goal

Provide an authenticated TLS device-ingress path, a bounded migration check,
and a rollback plan that never sends bearer credentials or location payloads
over plaintext in the target configuration.

# Serves

First-launch reliability/privacy; unblocks real-user-like field evidence.

# Acceptance Criteria

- [x] Target ESP-TLS firmware/tooling configuration uses an exact HTTPS origin,
      CA bundle and hostname verification. The unverified SIM7670 AT TLS path
      fails closed rather than being presented as complete.
- [x] Tests prove plaintext target configuration fails closed and secrets are
      redacted from logs/artifacts.
- [x] Migration keeps a time-bounded, explicitly labeled engineering fallback
      only for credential-free/body-free `GET /health`; production-style
      acceptance rejects it.
- [x] Deployment, credential rotation, rollback, and post-migration observation
      commands are documented and bounded.
- [x] OPS-004B provides a fixed-allowlist, query-only TLS capability mode and
      offline tests prove it cannot issue HTTP/network actions, TLS-setting
      writes, certificate uploads, tokens, or payload bodies.
- [ ] A newly operator-authorized hardware run records the exact SIM7670G
      firmware command surface; separate negative-path tests then prove invalid
      CA, hostname, clock and SNI cases fail closed.
- [x] Static/full validation passes before any operator-approved deployment.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Changed files:
  - `firmware/mqtt_heartbeat/main/app_main.c`
  - `firmware/mqtt_heartbeat/main/Kconfig.projbuild`
  - `firmware/mqtt_heartbeat/sdkconfig.vps_http.defaults.example`
  - `scripts/deploy_message_hub_vps.ps1`
  - `scripts/diag_lte_http_at.py`
  - `scripts/ops/nginx/ego.example.invalid.conf`
  - `tools/run_ft001b_imu_burst.py`
  - `docs/development/VPS_MESSAGE_HUB.md`
  - `docs/development/LTE_TRANSPORT.md`
  - `docs/operations/VPS_RUNBOOK.md`
  - `quality_tests/test_mqtt_heartbeat_firmware.py`
  - `quality_tests/test_lte_http_at_diag.py`
  - `quality_tests/test_vps_https_config.py`
  - this packet
- OPS-004B offline implementation (2026-09-02):
  `scripts/diag_lte_http_at.py --mode tls-capability` is a separate path that
  sends exactly `ATI`, `AT+CGMR`, `AT+CSSLCFG=?`, `AT+CSSLCFG?`,
  `AT+CCERTDOWN=?`, `AT+CCERTLIST`, and `AT+CCLK?`. It skips the existing LTE
  status/PDP and HTTP paths, never loads token material, and does not persist
  raw AT responses or certificate filenames. Parser, exact allowlist and
  zero-write/zero-traffic invariants have offline fixtures/tests. No live probe
  was run; it requires new explicit operator authorization.
- Official SIMCom evidence: the
  [SIM76XX SSL AT command manual](https://en.simcom.com/Uploads/file/20260622/20260622103004_43058.pdf)
  documents CA binding, server-auth mode, SNI, local-time checking and common-
  name checking for software `2388_SIM76XX` and later; the
  [SIM7600-series SSL application note](https://en.simcom.com/Uploads/file/20240611/20240611143858_59317.pdf)
  gives the native TLS flow. Current assessment is **documented capability /
  exact firmware + negative behavior unverified**.
- Validation after OPS-004B: focused LTE diagnostic tests `20/20 PASS`;
  Python compilation PASS; `scripts/context_lint.py` PASS; full
  `scripts/verify.ps1` `1059/1059 PASS`; scoped and repository-wide
  `git diff --check` PASS (unrelated working-tree line-ending warnings only).
- ESP-IDF compile (root integration, 2026-09-02): PASS for ESP32-S3 after
  explicitly selecting the installed IDF 5.4.2 Python/tool paths and using the
  tracked HTTPS defaults plus a non-secret placeholder token. The generated
  configuration has HTTPS enabled, exact host `ego.example.invalid`, CA bundle
  enabled and a nonempty placeholder credential; the placeholder is rejected
  by the runtime guard, so this image is build evidence only. Output:
  `tmp/ops004_build_20260902/egolink_mqtt_heartbeat.bin`, 982944 bytes,
  SHA-256
  `f6bdec900df297d571f33734127a18cce0ea17b2ccda3010f4a90d5c776711ae`.
  Five pre-existing configuration-dependent unused-symbol warnings remain;
  the build completed and produced both bootloader and application binaries.
  Nothing was flashed.
- Hardware/deployment result: `NOT_RUN`; no network, VPS, SIM, serial, flash,
  credential rotation or hardware operation was authorized or performed.
- Remaining risks/blocker: the current SIM7670 AT component has no integrated,
  reviewed CA-store plus hostname-verification implementation, so LTE ingress
  is deliberately stopped before token/payload transmission. The official
  command surface is documented, but its availability on the exact wearable
  modem firmware and its failure behavior are unverified. Device/modem clock,
  certificate provisioning, SNI/hostname behavior, TLS memory/power cost,
  reconnect/outbox behavior and the live VPS listener/firewall state all need
  separately authorized evidence. `P0-LOC`, `P0-CALL` and `P0-SOS` remain
  `NOT_RUN`.

# Builder Prompt

```text
Read docs/tasks/active/OPS-004_DEVICE_HTTPS_INGRESS.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files listed in this
packet's context. This is Lane C; do only this task, obey allowed_paths and
out_of_scope. Implement and test the authenticated TLS ingress configuration,
fail-closed plaintext production-style boundary, redaction, migration and
rollback plan. Do not deploy, rotate credentials, flash, or contact hardware.
Run every validation command and return changed files, exact output, evidence
paths and remaining hardware risks. Do not update STATUS or move this packet
to done.
```

Dispatch note: this packet is ready once the current working-tree candidate is
integrated/frozen. It does not wait for FT-001B, a hardware run, or
COMPLIANCE-010;
the short queue protects overlapping firmware/tool paths only.
