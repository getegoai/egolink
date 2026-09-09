---
id: CALL-021
title: Embedded LTE-data RTC media
status: paused
priority: critical
lane: B
execution_state: paused_by_founder_20260909
depends_on:
  - CALL-020
  - HW-022
serves_gate: P0-CALL
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-09

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md
  - docs/development/EGO_CALL.md
  - docs/hardware/P0_PRODUCT_ARCHITECTURE.md
  - docs/tasks/active/HW-022_INTEGRATED_PROTOTYPE_BUILD.md
  - docs/tasks/done/CALL-010_AUDIO_HARDWARE_LOOP.md
  - docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md

allowed_paths:
  - docs/tasks/active/CALL-021_EMBEDDED_LTE_RTC_MEDIA.md

out_of_scope:
  - implementation before an exact integrated hardware/data-bearer path is reviewed
  - PSTN, Native VoLTE, recording, multi-party calling, AI voice or polished App UI
  - interpreting PC bridge or USB media as embedded evidence
---

# 2026-09-09 Pause Boundary

ADR-0015 pauses CALL-021 with CALL-020 while the single-4G-board Location/
Camera field milestone runs. The embedded product requirement and all final
`P0-CALL` acceptance remain unchanged; no source or evidence is deleted.

# Goal

Remove the development PC and USB media bridge, then prove the actual P0 call
shape on one exact integrated prototype:

```text
device microphone/speaker
<-> embedded audio/RTC path
<-> SIM LTE data
<-> controlled RTC service
<-> Guardian endpoint
```

# Acceptance

- [ ] The prototype runs from independent product-like power; USB is absent
      from media, control and runtime evidence.
- [ ] Device -> Guardian and Guardian -> device audio pass the declared
      ten-minute full-duplex interval and setup/reconnect matrix over SIM LTE.
- [ ] Media/session state is authenticated, encrypted, bounded and replayable;
      exact board, modem firmware, SIM/operator, location, image and evidence
      identity are recorded.
- [ ] Failure and weak-network behavior are honest; no one-way or disconnected
      state remains labelled `connected`.
- [ ] The result still does not pass P0-CALL until product acoustic, power,
      reliability, identity/privacy and representative-day evidence also pass.

# Dispatch Boundary

Amend `allowed_paths` only after HW-022 provides the exact integrated target
and CALL-020 supplies measured codec/bitrate/jitter/traffic inputs. Flashing,
network changes and audio capture require explicit operator intent.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

Exact build/static/hardware commands are a dispatch input, not guessed now.

# Completion Evidence

- Changed files: pending exact topology selection and dispatch.
- Test/hardware/evidence: pending.
- Remaining risks: integrated bearer, power, RF, audio, RTC, security and
  representative-product behavior are unverified.

# Builder Prompt

```text
Read docs/tasks/active/CALL-021_EMBEDDED_LTE_RTC_MEDIA.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's
context. Begin only after CALL-020 and HW-022 are accepted. Freeze the exact
integrated prototype/data-bearer path and amend allowed_paths before editing
implementation. Remove the PC and USB from media, control and runtime evidence;
prove authenticated/encrypted two-way audio and bounded setup/recovery on
independent power. Flashing, SIM/network/RTC changes and audio capture require
explicit operator intent. Run every validation command plus the reviewed build,
fixture and hardware matrix; return board/modem/SIM/image/config identities,
exact outputs, evidence paths and remaining risks. Do not claim P0-CALL until
representative acoustic, power, reliability and privacy evidence also passes.
```
