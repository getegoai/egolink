---
id: HW-021
title: Exact integrated P0 prototype design and down-select
status: active
priority: critical
lane: D
execution_state: in_progress
depends_on:
  - HW-020
serves_gate: P0-LOC/P0-CALL/P0-SOS
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md
  - docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md

allowed_paths:
  - docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md
  - docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md
  - hardware/p0_a0/

out_of_scope:
  - purchasing, releasing fabrication data or powering hardware
  - treating a candidate table, ERC/DRC result or official datasheet as a built prototype
  - adding sensors, Native VoLTE or camera AI to the P0 critical path
---

# Goal

Turn HW-020's interface baseline into one reviewable, buildable integrated
prototype design with exact part/revision identities and explicit evidence.

# Acceptance

- [ ] Exact MCU, Cat.1/GNSS modem, IMU, audio codec/frontend, amp, microphones,
      speaker, persistent storage, SIM, charger/protection/gauge, battery,
      USB-C/debug and antenna candidates are named with official evidence.
- [ ] MCU-to-modem data bearer, full-duplex audio clocks/data, reset/wake,
      storage, SOS, power rails and test points have owned interfaces and
      bounded budgets; every unknown remains marked `unknown`/`unverified`.
- [ ] The design can absorb CALL-020 codec/bitrate/traffic/jitter measurements
      and COMPLIANCE-010 constraints without pretending those inputs already
      exist; unresolved choices are conditional release blockers.
- [ ] Reviewable schematic/BOM/net/power/RF/acoustic constraints and an
      independent EE/RF review checklist form one versioned engineering pack.
- [ ] No PCB release or hardware claim occurs in this task.

# Dispatch Boundary

This task can start immediately in parallel with CALL-020 and COMPLIANCE-010.
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
identities, CALL-020 measured inputs, final support parts, calculations,
schematic/BOM/layout and independent reviews remain open. The task therefore
stays `active` / `in_progress`.

# Blocking Decisions

1. Obtain SIMCom first-party evidence for the exact GNSS-enabled SIM7670G order
   code, HW/KDL revision, firmware, hardware-design manual and errata. Resolve
   the manufacturer's conflicting public sleep-current values; use neither in
   a budget meanwhile.
2. Feed measured CALL-020 codec/bitrate/frame/jitter/gap/reconnect/overhead
   results into the worksheet and prove the selected bearer on MCU + modem
   without a PC. UART+RTS/CTS is only a continuity hypothesis; USB ECM/RNDIS is
   only a conditional alternative.
3. Decide carry form, enclosure envelope, battery target and operator/channel;
   then obtain an exact battery-pack revision with pulse, impedance, NTC,
   protection and certification evidence.
4. Close audio clock/gain/speaker/acoustic/privacy behavior, outbox allocation
   and authenticated ACK semantics, rail/burst/thermal calculations, RF/body-
   loading constraints and missing support-part identities through independent
   review.
5. Receive the qualified COMPLIANCE-010 response before RF/layout or release
   assumptions are frozen.
6. Record an explicit PICO-versus-WROOM A0 decision. The C0.1 WROOM candidates
   do not silently supersede the Master Context's PICO engineering starting
   point.
7. Obtain comparable exact-SKU evidence and record an explicit modem decision;
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
  candidates and exact missing identities without making a selection.
- `hardware/p0_a0/HW021_C0_1_INTERFACE_BUDGETS.md` records conditional bearer,
  audio, storage, power, SIM/debug/RF ownership and unknown inputs.
- `hardware/p0_a0/HW021_C0_1_REVIEW_CHECKLIST.md` keeps every release and
  representative-evidence check open.
- Hardware: `NOT_RUN`; this task cannot claim a prototype exists.
- Gates: integrated-hardware `P0-LOC`, `P0-CALL`, `P0-SOS` are `NOT_RUN`.
- Remaining risks: the blocking decisions above prevent final down-select,
  schematic/BOM/layout review, procurement, fabrication and HW-022 dispatch.
