---
id: HW-022
title: Integrated P0 prototype build and bring-up
status: active
priority: critical
lane: D
execution_state: in_progress
depends_on:
  - HW-021
  - CALL-030
serves_gate: P0-LOC/P0-CALL/P0-SOS
requires_hardware: true
created: 2026-08-23
last_updated: 2026-10-20

context:
  - docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md
  - docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md
  - docs/tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md
  - docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md

allowed_paths:
  - docs/tasks/active/HW-022_INTEGRATED_PROTOTYPE_BUILD.md
  - docs/hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md
  - firmware/hw021_pcb1_bringup/

out_of_scope:
  - purchasing, fabrication, assembly, power-up, flash or RF/audio drive
    without explicit founder/operator intent
  - claiming A0 bring-up is a saleable product or production BOM freeze
---

## 2026-09-22 primary-cellular dependency alignment

ADR-0016 replaces the old RTC primary-path dependency with CALL-030 feasibility
and CALL-031 native cellular product evidence. CALL-020/021 remain paused RTC
assets. The criteria below retain their reliability/privacy/product invariants;
current references to Ego Call mean native cellular primary, with RTC auxiliary.
Historical implementation checkpoints remain dated evidence, not a new result.
No Gate or hardware state advances from this dependency update.


# Goal

Build and bring up one independently powered integrated prototype that gives
CALL-031, LOC-021 and SOS-010 a real PC/USB-free execution target.

# Acceptance

- [ ] Fabricated/assembled unit and every rework are bound to design/BOM/CPL,
      serial/revision, date, owner and private evidence paths.
- [ ] Power sequencing, brownout recovery, MCU/modem bearer, GNSS/LTE, audio
      RX/TX, persistent storage, SOS key and local feedback pass bounded
      bring-up without borrowing split-development-board evidence.
- [ ] USB is absent from product media/control evidence; independent power and
      debug boundaries are explicit.
- [ ] CALL-030 cellular/audio/power interface inputs and current pre-compliance
      constraints are traced into the built revision or recorded as blockers.
- [ ] Failures remain visible; this task alone cannot pass any P0 Gate.

# Dispatch Boundary

At dispatch, amend `allowed_paths` with the exact design, build record and
private evidence locations plus bounded commands. Procurement, fab release,
power-up, flash, SIM traffic and audio/RF activity each require explicit
founder/operator intent.

# Validation

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- **2026-10-20 `PCB1` (`HW021_C1_ESP32MODEL_VR00`) Initial Bring-Up (`COM8`)**:
  - Schematic (`hardware/PCB1/HW021_C1_ESP32MODEL_VR00.pdf`), assembly photos (`hardware/PCB1/1.jpg`–`5.jpg`), and live 10-stage hardware bring-up documented in [HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md](../../hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md).
  - Verified on `COM8` (`ESP32-S3R8` MAC `02:00:00:00:00:02`, Winbond `W25Q32JVSQ` 4 MiB flash `0xef4016`): battery high-side switch & ADC (`4242 mV`), buttons (`GPIO0/6`), `SC7A20TR` G-sensor (`0x19`, `WHO_AM_I=0x11`, 50 Hz 1g), `J8` I2C1 pull-ups, `Beitian BE-220` GNSS (`115200` baud NMEA), `ML307A-DSLN-MTSH1S00` 4G modem AT & VoLTE/audio command support (`+CAVIMS: 1`, `AT+CLCC`, `AT+VTS`, `AT+CMUT`, `AT*Audio`), and 2.4 GHz Wi-Fi RF scan (7 APs, `-51 dBm`).
- **Remaining Risks & Rework Blockers**:
  1. `J9` camera `TWI_SDA (GPIO8)` and `TWI_CLK (GPIO7)` are shorted directly to `3.3V_VCC` on the schematic/PCB (`clk_od_low=1, sda_od_low=1`), requiring trace-cut rework before `OV2640` capture can pass.
  2. `U6 (TP4057)` `R30 = 2K` (`500 mA`) must be reworked to `5.1K–10K` (`100–200 mA`) for the `200 mAh` LiPo battery (`2.5C` hazard).
  3. `R28 = 0R` shorting `ML307A` `SPK_N` to `GND` must be removed before acoustic speaker tests.
  4. SIM card insertion, outdoor GNSS fix, and USB-free battery runtime acceptance remain pending.
