---
id: HW-021
title: Exact integrated P0 prototype design and down-select
status: active
priority: critical
lane: D
execution_state: parked
depends_on:
  - HW-020
serves_gate: P0-LOC/P0-CALL/P0-SOS
requires_hardware: false
created: 2026-08-23
last_updated: 2026-09-09

context:
  - docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/tasks/active/P0-CONVERGENCE-20260905.md
  - docs/tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md
  - docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md

allowed_paths:
  - docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md
  - docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md
  - hardware/p0_a0/

out_of_scope:
  - purchasing, releasing fabrication data or powering hardware
  - treating a candidate table, ERC/DRC result or official datasheet as a built prototype
  - adding sensors or camera AI to the P0 critical path; native cellular primary is already required by ADR-0016
owner: unassigned
reviewed_at: 2026-09-22
---

# Goal

Turn HW-020's interface baseline into one reviewable, buildable integrated
prototype design with exact part/revision identities and explicit evidence.

# Acceptance

- [ ] Exact MCU, Cat.1/GNSS modem, IMU, Camera, audio codec/frontend, amp,
      microphones, speaker, persistent storage, SIM, charger/protection/gauge,
      battery, USB-C/debug and antenna candidates are named with official
      evidence.
- [ ] MCU-to-modem data bearer, full-duplex audio clocks/data, reset/wake,
      Camera data/control/power, storage, SOS, power rails and test points have
      owned interfaces and bounded budgets; every unknown remains marked
      `unknown`/`unverified`.
- [ ] Camera pin/bus conflicts, standby/PWDN or power-cut capability, lens/FOV
      and mounting direction, enclosure opening/sealing, JPEG RAM/storage and
      LTE-upload budgets are explicit design inputs rather than inferred from
      a development-board smoke.
- [ ] The design can absorb CALL-030 native call/control/audio feasibility and
      separately measured product data/traffic/recovery requirements
      and COMPLIANCE-010 constraints without pretending those inputs already
      exist; unresolved choices are conditional release blockers.
- [ ] Reviewable schematic/BOM/net/power/RF/acoustic constraints and an
      independent EE/RF review checklist form one versioned engineering pack.
- [ ] No PCB release or hardware claim occurs in this task.

# Dispatch Boundary

This task is parked with no assigned active builder. On explicit dispatch it
may proceed in parallel with Gemini's A-line and COMPLIANCE-010. CALL-030 is
the current native call/control/audio input; missing evidence blocks relevant
release closure, while unrelated Camera, RF, power, storage or mechanical
design can proceed. CALL-020/021 remain paused optional RTC work and are not
implicit prerequisites for the native path.
Before creating design-source files, confirm the exact `hardware/p0_a0/`
structure and add its local instructions if needed. Web/vendor facts require
primary official sources; purchasing and fabrication require separate founder
authorization.

# C0.1 Design Slice

The first read-only design slice is present under `hardware/p0_a0/` as pack
revision `HW021-C0.1`. It contains:

- a manufacturer-primary-source candidate matrix with exact order codes where
  public evidence supports them and explicit `identity_incomplete`/
  `unverified` states elsewhere;
- conditional MCU-to-modem UART versus USB bearer inputs, full-duplex Ego Call
  audio ownership, persistent priority-outbox capacity rules, power/SIM/debug/
  RF constraints and required test points;
- an independent EE/RF/audio/mechanical/privacy/compliance release checklist.

This slice does not complete any acceptance item: the exact modem/battery
identities, CALL-030 native feasibility, measured data inputs, final support parts, calculations,
schematic/BOM/layout and independent reviews remain open. The task therefore
stays lifecycle `active`, execution `parked`, pending assigned dispatch.

## 2026-09-09 Camera Design-Input Overlay

ADR-0015 makes Camera a required input to this design track while leaving
visual inference outside the first-release Gate path. Reuse of the historical
OV5640/QVGA camera-smoke route proves only that three JPEGs were captured on one
development setup; it neither selects a production Camera nor proves current
combined-firmware, pin, power, storage, LTE or enclosure behavior.

A line must feed C the exact observed Camera module/revision and wiring,
resolution and JPEG-size distribution, initialization/capture/save/upload
latencies, heap/PSRAM/task watermarks, persistent-storage growth and measured
power/standby behavior where available. C must resolve the Camera-versus-IMU/
gauge bus and pin ownership, controllable power state, lens direction and FOV,
window/occlusion/sealing, thermal/RF coupling, storage quota and uplink budget.
Unmeasured values remain `unknown`/`unverified`; a development OV5640 does not
silently become the product BOM choice.

### C0.1 Camera Audit Result

The current combined-firmware design exposes useful constraints without
closing a product choice:

- the development map consumes D0-D7 GPIO7-14, shared I2C0 GPIO15/16, XCLK
  GPIO39, HREF GPIO41, VSYNC GPIO42 and PCLK GPIO46; PCLK conflicts with the
  board TF-detect path, while GPIO39-42 must remain free of external JTAG in
  the A-line test;
- the configured QVGA/JPEG path uses one internal-DRAM framebuffer and no
  Camera PWDN/reset GPIO, so driver deinit is not physical standby or power-off
  evidence;
- the 9-MiB engineering image store contains 288 fixed 32-KiB slots. At five
  minutes per image this is exactly 24 hours with zero photo-count margin;
- the allocator can repeatedly reuse a low-numbered slot after immediate ACK
  release, and boot initialization scans the complete owned media range, so
  endurance/wear distribution and boot-time/energy are explicit inputs;
- the engineering map has one factory app, no A/B OTA layout, and unencrypted
  raw JPEG storage. A product media part, secure retention design and complete
  OTA/storage budget remain `unknown`.

These facts are now represented in the C0.1 source gaps, interface/budget
worksheet and independent review checklist. They do not advance a hardware or
P0 Gate.

### Required A-to-C Camera Handoff

Each named authorized A-line run must return the physical board/Camera/lens/
FPC/IMU/power identities and wiring; exact firmware/config/binary/partition
identity; JPEG distribution; initialization, frame, save, deinit and upload
latencies; internal/DMA heap and task-stack watermarks; sensor/bus/reset error
evidence; storage growth, slot use, write/erase and boot-scan behavior;
Wi-Fi/LTE traffic and ordinary-observation continuity; measured Camera/idle/
upload power where available; and actual lens direction/FOV/occlusion/window
state. Privacy authorization, retention/deletion and evidence paths remain
part of the handoff. Missing measurements stay `unknown` and do not stop
unrelated C-line work.

# Blocking Decisions

1. Obtain SIMCom first-party evidence for the exact GNSS-enabled SIM7670G order
   code, HW/KDL revision, firmware, hardware-design manual and errata. Resolve
   the manufacturer's conflicting public sleep-current values; use neither in
   a budget meanwhile.
2. Feed CALL-030's exact native control/audio feasibility into the worksheet;
   determine analog/PCM/I2S compatibility, clock/control ownership and complete
   microphone/speaker routing. Separately measure product data load/recovery
   and prove the selected bearer on MCU + modem without a PC. Missing fields
   stay unknown; UART+RTS/CTS and USB ECM/RNDIS remain conditional alternatives.
   Legacy RTC measurements may be reused only within their actual evidence
   scope and do not automatically resume CALL-020/021.
3. Resolve Camera/IMU/gauge interface ownership and obtain the measured A-line
   Camera resource, persistence, transfer, power and mechanical inputs listed
   above. Close the product image-media part, endurance/wear, encryption,
   hard-power/privacy, OTA-capacity, RF and optical/sealing inputs. Select a
   production Camera only through the normal evidence review.
4. Decide carry form, enclosure envelope, battery target and operator/channel;
   then obtain an exact battery-pack revision with pulse, impedance, NTC,
   protection and certification evidence.
5. Close audio clock/gain/speaker/acoustic/privacy behavior, outbox allocation
   and authenticated ACK semantics, rail/burst/thermal calculations, RF/body-
   loading constraints and missing support-part identities through independent
   review.
6. Receive the qualified COMPLIANCE-010 response before RF/layout or release
   assumptions are frozen.
7. Record an explicit PICO-versus-WROOM A0 decision. The C0.1 WROOM candidates
   do not silently supersede the Master Context's PICO engineering starting
   point.
8. Obtain comparable exact-SKU evidence and record an explicit modem decision;
   SIM7670G continuity cannot silently supersede the Master Context's still-
   unverified `ML307A-GSLN` lead or the China operator/compliance requirements.

# Validation

```powershell
python scripts/context_lint.py
git diff --check -- docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md hardware/p0_a0
```

Full-repository `scripts/verify.ps1` is intentionally outside this focused
documentation slice and is not evidence for hardware behavior.

# Completion Evidence

- `hardware/p0_a0/HW021_C0_1_SOURCE_MATRIX.md` records official-source
  candidates and exact missing identities, including the deliberately unnamed
  Camera module/lens/media-store gap, without making a selection.
- `hardware/p0_a0/HW021_C0_1_INTERFACE_BUDGETS.md` records conditional bearer,
  audio, Camera/image-media, storage, power, SIM/debug/RF ownership and unknown
  inputs.
- `hardware/p0_a0/HW021_C0_1_REVIEW_CHECKLIST.md` keeps every release and
  representative-evidence check open, including Camera power, optics, media,
  endurance, privacy and coexistence.
- Hardware: `NOT_RUN`; this task cannot claim a prototype exists.
- Gates: integrated-hardware `P0-LOC`, `P0-CALL`, `P0-SOS` are `NOT_RUN`.
- Remaining risks: the blocking decisions above prevent final down-select,
  schematic/BOM/layout review, procurement, fabrication and HW-022 dispatch.
