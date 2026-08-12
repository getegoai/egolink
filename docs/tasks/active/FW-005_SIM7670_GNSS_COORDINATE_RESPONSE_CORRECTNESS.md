---
id: FW-005
title: SIM7670 GNSS coordinate and response correctness
status: active
priority: high
requires_hardware: false
serves_demo: D2-D5
created: 2026-08-12
last_updated: 2026-08-12

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/DEV_FLOW.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/AGENTS.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - firmware/mqtt_heartbeat/components/sim7670_gnss/include/sim7670_gnss.h
  - quality_tests/AGENTS.md
  - quality_tests/test_fw002b_sim7670_gnss_firmware.py
  - scripts/sim7670_gnss_probe.py
  - quality_tests/test_sim7670_gnss_probe.py

allowed_paths:
  - docs/tasks/active/FW-005_SIM7670_GNSS_COORDINATE_RESPONSE_CORRECTNESS.md
  - firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c
  - firmware/mqtt_heartbeat/components/sim7670_gnss/include/sim7670_gnss.h
  - quality_tests/test_fw002b_sim7670_gnss_firmware.py
  - quality_tests/test_sim7670_gnss*.py
  - scripts/sim7670_gnss_probe.py
  - quality_tests/test_sim7670_gnss_probe.py
  - firmware/mqtt_heartbeat/build_*

out_of_scope:
  - firmware flashing, modem control, or field validation
  - wire protocol, server, Dashboard, or historical-database mutation
  - GNSS acquisition policy, A-GNSS, RF tuning, or hybrid-location implementation
---

# Goal

Correct SIM7670 GNSS coordinates and retain complete bounded GNSS AT responses
before another location-accuracy run.

# Expected Result

- Parse `+CGNSSINFO` coordinates as decimal degrees and `+CGPSINFO`
  coordinates as degrees/minutes, with strict hemisphere, finite-number,
  minute, and latitude/longitude range validation.
- For GNSS information queries, keep reading after the response prefix until
  the complete response line and terminal `OK` or `ERROR` arrive, without
  changing the generic LTE/HTTP AT behavior.
- Keep the PC-side diagnostic parser aligned with the firmware parser so the
  same response does not produce two coordinate interpretations.
- Protect the observed FIELD-011 decimal-degree shape with synthetic,
  non-private coordinates and a full quality tail in executable parser tests.

# Acceptance Criteria

- [ ] A synthetic decimal-degree `+CGNSSINFO` sample remains unchanged after
      parsing; `+CGPSINFO` degree/minute behavior does not regress.
- [ ] Empty, truncated, non-finite, malformed-hemisphere, invalid-minute,
      out-of-range, and non-fix-mode inputs fail closed.
- [ ] A GNSS response split across UART-sized chunks is not considered
      complete at the prefix and retains PDOP/HDOP/VDOP/satellite fields.
- [ ] Focused tests, ESP-IDF 5.4.2 build-only, full verification, context lint,
      and diff check pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_fw002b_sim7670_gnss_firmware quality_tests.test_sim7670_gnss_parser -v
. C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1
Push-Location firmware\mqtt_heartbeat
try { idf.py -B build_fw005_gnss_correctness build } finally { Pop-Location }
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\context_lint.py
git diff --check
```

# Hardware Validation

Not authorized or required in this static slice. A later bounded flash and
open-sky A/B run must provide the hardware evidence.

# Completion Evidence

- Changed files: pending.
- Test result: pending.
- Hardware result: not run.
- Remaining risks: RF occlusion, acquisition policy, A-GNSS capability, and
  historical bad-coordinate remediation remain separate work.

# Builder Prompt

```text
Read docs/tasks/active/FW-005_SIM7670_GNSS_COORDINATE_RESPONSE_CORRECTNESS.md
in D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, this packet,
and its context entries. Correct only coordinate parsing and bounded complete
GNSS AT response collection; obey allowed_paths and out_of_scope. Run all
declared validation commands. Do not flash, open hardware ports, change wire
contracts, mutate historical data, or add hybrid-location behavior. Return
changed files, validation results, and remaining risks.
```
