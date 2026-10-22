---
id: CALL-030
title: Native cellular feasibility and audio interface
status: active
execution_state: in_progress
owner: gemini
priority: high
lane: B
depends_on: []
serves_gate: P0-CALL
requires_hardware: true
created: 2026-09-22
last_updated: 2026-10-20
context:
  - docs/CONTEXT_INDEX.md
  - docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md
  - shared/contracts/
allowed_paths:
  - docs/tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md
  - docs/hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md
  - firmware/hw021_pcb1_bringup/
out_of_scope:
  - implementation outside a reviewed dispatch amendment
  - hardware I/O, purchases, deployment, real data migration/deletion or external contact without task-specific authority
  - changing any Gate from NOT_RUN without its representative acceptance
---

# Goal

Name the exact modem, firmware, operator/SIM and audio interface needed for the
primary native cellular path. Preserve CALL-020/021 as paused RTC research assets.
The current audio-less connectivity board cannot prove acoustic closure.

# Acceptance

- [ ] Official/exact-board capability inputs and unknowns are traceable; no capability is inferred from the board name.
- [ ] AT ready/configuration failure, dial/answer/hangup/cancel and contact authorization have a bounded offline plan and executable acceptance cases.
- [ ] Audio/power/RF inputs and measured or explicitly unknown budgets are handed to HW-021/HW-022.
- [ ] A separately authorized signal-only probe, if performed, is separated from full-duplex audio evidence.

# Dispatch and validation

Queued, not assigned implementation WIP. At dispatch, assign the owner, exact
implementation/evidence paths and bounded experiment scope; reuse current
components and preserve Gemini's acquisition/recovery/field path.

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion evidence

- **2026-10-20 Hardware & Firmware Feasibility Verified on `PCB1` (`COM8`)**:
  - Exact cellular modem populated on `HW021_C1_ESP32MODEL_VR00` (`PCB1`, `U1`): **CMCC `ML307A-DSLN`**, firmware revision **`ML307A-DSLN-MTSH1S00`** (`UART2` on `TX1=GPIO36`, `RX1=GPIO37`, power switch `4G_PWDN=GPIO15`, status `NETLIGHT=GPIO35`).
  - Analog audio interface on `PCB1`: `ML307A-DSLN` Pins 3–4 (`MIC_P`/`MIC_N`) wired to `J4` electret microphone; Pins 5–6 (`SPK_P`/`SPK_N`) wired to `U5 (8002A)` amplifier (`MUTE=GPIO5`) -> `J5` speaker (requires removing `R28=0R` on `SPK_N` per ECN-05).
  - Live AT & `AT+CLAC` probe on `COM8` (`reports/board_validation/pcb1_bringup_20261020/bringup_serial_final.log`, [full report](../../hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md)) proved native VoLTE/IMS voice and analog audio support:
    - `AT+CAVIMS?` -> `+CAVIMS: 1 OK`
    - `AT+CIREG?` -> `+CIREG: 1,0,0 OK`
    - `AT+CEVDP?` -> `+CEVDP: 3 OK`
    - `AT+CEMODE?` -> `+CEMODE: 2 OK`
    - `AT+CLCC` -> `OK`, `AT+CLIP=?` -> `+CLIP: (0-1) OK`, `AT+VTS=?` -> `+VTS: <DTMF>, (20-1000) OK`, `AT+CMUT=?` -> `+CMUT: 0,1 OK`
    - `AT*Audio=?` -> `*Audio: OK`, `AT*AUDNVM?` -> `OK`
    - `AT+CLAC` confirmed `ATA`, `ATD`, `ATH`, `AT+CHUP`, `AT+TRUSTNUM`, `AT+CHKTRUSTNUM`, `AT+MTTSCFG/PLAY/STOP`, `AT+MAUDPLFILE`, `AT+MAUDRECFILE`.
- **Remaining to close `CALL-030`**: Insert VoLTE-enabled SIM card into `CON1`, remove `R28 (0R)`, and execute live SIM registration + inbound/outbound acoustic voice test (`P0-CALL` remains `NOT_RUN`).

# Builder Prompt

Read this packet and its context. Prepare one bounded implementation slice and
its allowed paths before editing source. Keep hardware/data/remote operations
inside their explicit task scope and record truth separately from predictions.
