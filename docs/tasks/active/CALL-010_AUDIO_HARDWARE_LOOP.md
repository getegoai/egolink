---
id: CALL-010
title: Wearable audio I/O and simultaneous-loop bring-up
status: active
priority: critical
lane: B
execution_state: accepted_for_transition
depends_on:
  - CALL-001
serves_gate: P0-CALL
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-02

context:
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/tasks/active/CALL-001_EGO_CALL_ARCHITECTURE_AND_PC_LOOP.md

allowed_paths:
  - docs/tasks/active/CALL-010_AUDIO_HARDWARE_LOOP.md
  - docs/development/EGO_CALL.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/tasks/TASK_TREE.md
  - docs/hardware/BOARD_MATRIX.md
  - firmware/audio_loop/
  - quality_tests/test_audio_loop_firmware.py
  - reports/board_validation/CALL-010-20260902-001/
  - reports/board_validation/CALL-010-20260902-002/
  - reports/board_validation/CALL-010-20260902-003/
  - reports/board_validation/CALL-010-20260902-004/
  - reports/board_validation/CALL-010-20260902-005/
  - reports/board_validation/CALL-010-20260902-006/
  - reports/board_validation/CALL-010-20260902-007/
  - reports/board_validation/CALL-010-20260902-008/

out_of_scope:
  - LTE transport, RTC, PSTN, VoLTE, recording or AI voice
  - changing mqtt_heartbeat or existing board pin assignments
  - claiming audio hardware works before an operator-approved run
---

# Exact Engineering Path

```text
wearable-node-001 onboard microphones
-> ES7210 -> I2S RX -> one overwritten bounded PCM frame
-> I2S TX -> ES8311 -> NS4150B -> main-board P5/P6 SPK contacts
-> product/enclosure speaker
```

Official board material is bring-up input only. Runs
`CALL-010-20260902-006` and `-007` now provide bounded logical runtime
evidence for the repository-mapped path. Run 007's physical acoustic output
failed the operator check. The operator confirmed speaking during run 007's
30-second input phase, and the digital metric change is therefore correlated
with a known spoken stimulus; this does not establish physical channel mapping,
audio quality or a concurrent acoustic loop. Output-only run
`CALL-010-20260902-008` completed staged volume `55/70/85` logical output and
final-safe markers without constructing or reading a microphone. The operator
subsequently confirmed that the bounded sequence sounded clear and normal
overall, without identifying individual stages; no painful or distorted result
was reported. The speaker-output audibility debug
issue is therefore resolved for this development-board slice. Its strict result
remains `FAIL_OR_INCOMPLETE` because one initialization error-level diagnostic
was captured; the acoustic PASS does not waive that diagnostic. Together with
the operator-confirmed spoken-stimulus/input-metric response from run 007, the
basic development-board audio endpoints are sufficient to unlock CALL-020 while
the stricter CALL-010 closure items remain open.

# Goal

On one exact audio-capable development board, prove microphone capture and
speaker playback separately, then concurrently, using a new isolated firmware
target with explicit source/board identity.

# Acceptance

- [ ] Static design records the exact physical board revision, codec/ADC/amp/
      I2S path, dependency versions and source status.
- [x] Build is reproducible without modifying another firmware target.
- [ ] Operator-approved evidence proves 30-second output, 30-second input and
      120-second simultaneous RX/TX without reset, sustained silence/clipping,
      DMA underrun/overrun or false source claims.
- [x] Evidence records board, firmware/image, connection, time and paths.
- [ ] A known chirp is measurable and produces an engineering local-loop delay
      metric; this does not close AEC/AGC/SPL/echo/product acoustic gates.

# Validation Commands

```powershell
python -m unittest quality_tests.test_audio_loop_firmware -v
powershell -NoProfile -ExecutionPolicy Bypass -Command {
  . C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1
  Push-Location firmware\audio_loop
  try {
    idf.py -B build_static build
    idf.py -B build_operator_static `
      -D "SDKCONFIG=$PWD/build_operator_static/sdkconfig" `
      -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.operator_test.defaults" `
      build
    idf.py -B build_output_diagnostic_static `
      -D "SDKCONFIG=$PWD/build_output_diagnostic_static/sdkconfig" `
      -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.output_diagnostic.defaults" `
      build
  } finally { Pop-Location }
}
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

The isolated static target and focused-test paths are dispatched. These
commands authorize build/static verification only, never flash or run.

# Hardware Boundary

Build/static preparation may proceed after dispatch. Flashing, microphone capture and
speaker output require explicit operator intent. Default hardware execution is
low volume with a bounded automatic mute/PA-off timeout; ordinary voice is not
retained by default.

Operator-authorized bounded hardware runs have been executed and retained. The
task is `accepted_for_transition`; any further microphone capture, speaker
drive or flash/run attempt still requires new explicit operator intent.

# Completion Evidence

- Changed files: isolated `firmware/audio_loop/` target, versioned local safe
  initializer, pinned dependency lock, static contract test, and this packet.
  No existing firmware target or ignored managed component changed.
- Focused test: `python -m unittest quality_tests.test_audio_loop_firmware -v`
  passed `8/8` on 2026-09-02, including the guarded controlled-start and
  output-diagnostic contracts.
- Final validation on 2026-09-02: ESP-IDF `v5.4.2` dormant/operator/output-
  diagnostic builds passed; `powershell -File scripts/verify.ps1` passed
  `932/932`;
  `python scripts/context_lint.py` and `git diff --check` passed. The Git
  check reported only pre-existing line-ending conversion warnings.
- Static builds: ESP-IDF `v5.4.2` passed with both the default dormant config
  and a separately generated operator-test compile profile. The current
  dormant image is `195408` bytes, SHA-256
  `98829A1E1CFA1002C3C4C3FACC313E92B8F0A6E7629851D6DE2743FC0150984C`;
  the operator-test image used by the retained logical-runtime evidence is
  `278800` bytes, SHA-256
  `327485660B436ABCEBE166586581C184C5164EAF7A1EC1B030EC4D20701976BB`.
  Its ELF retains the local initializer/deinitializer, ES8311/ES7210
  constructors and codec read/write symbols; it contains zero BSP speaker or
  microphone constructor symbols. The dormant ELF contains zero active-path
  initializer/codec/read/write symbols.
- Static PA result: `call010-safe-audio-init-v1` uses BSP public I2C and board
  pin macros, constructs one shared I2S data interface, configures ES8311 with
  `pa_pin=-1`, and gives application code sole ownership of
  `BSP_POWER_AMP_IO`. The pinned BSP constructor-before-mute path is no longer
  reachable from this isolated target. Both profiles preload and configure PA
  low, verify the low level, and fail closed before the default dormant/autorun
  branch is evaluated.
- Hardware result/evidence: guarded attempts are retained under
  `reports/board_validation/CALL-010-20260902-001/` through `-008/`.
  Attempts 001 and 003 stopped before flash. Attempt 002 failed closed before
  any phase when ES8311 mute readback did not match, with PA OFF verified.
  Attempt 004 was incomplete because the application started before serial
  capture and its one-run latch then correctly prevented replay. Attempt 005
  verified a dormant disarm image. Attempt 006 used esptool
  `--after no_reset`, opened the serial evidence path before one RTS reset and
  completed all three phases: output `1500/1500`, input `1500/1500`, and
  attenuated local loop `6000/6000`, with zero phase-metric read errors, write
  errors or frame gaps, no fatal marker, and final `ESP_OK`, PA OFF verified
  and no deadline expiry. Both logical input channels had low but nonzero PCM
  metrics and zero clipping; those values may be noise floor and do not prove
  physical microphone pickup. Initialization also emitted two
  `i2s_channel_disable ... channel has not been enabled yet` error-level
  diagnostics, which remain unresolved. No raw audio was retained, and the 4G
  board was not changed.
- Follow-up result/evidence: attempt 007 repeated the same controlled-start
  `30/30/120`-second sequence on the same COM8/MAC target and operator image.
  All logical phase and final-safe checks passed. The operator subsequently
  confirmed that no sound was heard during the entire run, so attempt 007's
  acoustic output result is `FAIL`. During the nominal input window where
  speech had been requested, both logical-channel RMS values rose to
  approximately ten times the low attempt-006 baseline and their peaks also
  increased. The operator has now confirmed speaking during that 30-second
  window, so the stimulus and digital metric change are correlated input-path
  evidence. They do not establish physical microphone/channel mapping,
  calibrated sensitivity, audio quality or a concurrent acoustic loop.
  Attempt 007 retained no raw audio and emitted the same two unresolved
  initialization diagnostics.
- Output-only result/evidence: attempt 008 used a separate `278960`-byte image
  with SHA-256
  `014207FD036987A4DD3FA1EE26CFD51944FE3C5EEF04B40BEDD7A983E97F0B0A`.
  After a 15-second PA-off/muted countdown, the 1 kHz, PCM-peak-5000 reference
  ran for two seconds each at volume `55`, `70`, and `85`, with two-second
  muted/PA-off gaps. Each stage completed `100/100` frames and
  `128000/128000` requested/actual bytes, with matching ES8311 register
  readback `0x99`, `0xa8`, and `0xb7`. No microphone was constructed or read,
  no raw audio was retained, no fatal/deadline marker occurred, and the final
  PA-off marker passed. The granular runtime result is
  `PASS_ALL_STAGES_AND_FINAL_SAFE`; the strict runner result remains
  `FAIL_OR_INCOMPLETE` solely because one upstream initialization-time
  `i2s_channel_disable ... channel has not been enabled yet` error-level line
  was captured. The operator subsequently confirmed that the high-volume
  sequence sounded clear and normal overall and reported no painful or
  distorted result; the operator did not identify the three stages separately.
  This is an acoustic speaker-output `PASS` for the
  bounded development-board slice, not an SPL or product-acoustics measurement.
  The 4G board was not targeted.
- Post-run offline fix/build: the output-diagnostic-only path now pre-arms TX
  while PA is forced low before codec open, removing the known first-open
  blind-disable cause without enabling RX. Focused tests passed `8/8`, and
  ESP-IDF `v5.4.2` built a new `279280`-byte image with SHA-256
  `B79C6E0B5B5EF76165DF5FA2DF3DDE82786E7C8EC20D5B4C5D97E8427FF3DAC8`.
  This image was **not** flashed or run, does not revise attempt 008's strict
  result, and provides no additional hardware evidence. No further hardware
  run is authorized.
- Restore evidence: after a verified dormant restore, UI-001 was rebuilt and
  restored to the same COM8/MAC target. Its `659120`-byte application SHA-256
  is `11D72868A956E86F7B91D1B9D6008404FBD02B61299D566399DDC90F50A23139`;
  all bootloader, partition-table and application writes passed hash
  verification. Boot evidence observed `hello` and `display_ready`, and the
  bounded smoke observed `status_rendered` and `ask_user_rendered`. UI-001 was
  restored again after attempt 007. It was restored once more after attempt
  008: all three writes passed hash verification, bounded boot observed
  `hello` and `display_ready`, and smoke `UI001-RESTORE-20260902-008` passed
  `status_rendered` and `ask_user_rendered`. Evidence is in the
  `restore_ui001_*` files and `ui001_smoke/` below attempts 006 through 008.
- Remaining risks: exact physical PCB revision, the two physical
  microphone/channel mapping, calibrated audio level, application audio,
  product acoustics, power and the integrated product path remain unverified.
  Attempt 007's weak output stimulus failed its hearing check, while attempt
  008 provides the later operator-confirmed clear/normal speaker-output PASS.
  The known chirp was not externally measured, the current
  single-frame capture-then-play loop does not measure acoustic loop delay,
  DMA underrun/overrun or application-level concurrent queues, and
  processing-time P95 was about `30-31 ms`. Attempt 007's operator-confirmed
  spoken stimulus and correlated input-metric increase do not remove those
  limitations. Attempt 008's initialization diagnostic remains part of the
  retained run even though the unflashed post-run candidate addresses the
  identified first-open cause. The runs therefore cannot close the
  simultaneous-I/O or chirp/delay acceptance items. CALL-010 remains active but
  is `accepted_for_transition`: its basic audio endpoints no longer block
  CALL-020. `P0-CALL` remains `NOT_RUN`.

- Post-run gain/topology audit: volume `12` mapped to `-44 dB` through the
  pinned default curve and, after its declared gain compensation, to the
  verified ES8311 register `0x6e` (approximately `-40.5 dB`). The chirp peak
  `1800/32767` was approximately `-25.2 dBFS`, giving a nominal combined level
  about `-65.7 dB` below the corresponding full-scale codec path before the
  external amplifier. The loop's `/16` attenuation added approximately
  `-24.1 dB`. The official Arduino `08_ES8311` example uses volume `85`, so
  attempt 007 was not a decisive hardware-output stimulus. The official
  product describes an internal speaker, but the V1.0 main-board schematic
  terminates NS4150B differential output at `P5/P6` contacts marked `SPK`.
  The operator confirmed a complete enclosure and supplied external photos
  showing visible acoustic openings; the photos do not verify the internal
  speaker assembly or `P5/P6` contact.

# Immediate Next Slice

The basic speaker endpoint is now operator-confirmed working clearly and
normally under the bounded run-008 stimulus, so the conditional P5/P6/PA/codec
hardware trace is no longer the active branch. The input response and speaker
output are sufficient to transition the mainline to CALL-020. CALL-010's
remaining, non-transition-blocking closure work is narrowed to:

1. implement and statically verify real application-level simultaneous RX/TX
   queues with explicit DMA underrun/overrun accounting;
2. define a measurable known-chirp/local-loop delay method that does not retain
   ordinary raw audio;
3. obtain separate operator authorization before flashing/running the offline
   TX-prearm candidate or performing any further microphone/speaker exercise;
4. retain the run-008 strict `FAIL_OR_INCOMPLETE` result until a new authorized
   runtime shows that the initialization diagnostic is absent;
5. let CALL-020 own LTE-data/VPS/browser voice-chain proof, while the separate
   downstream acceptance tasks retain RTC/product-call and `P0-CALL` closure.

These are planned follow-ups only. No new hardware action is authorized by this
packet update.

# Builder Prompt

```text
Read docs/tasks/active/CALL-010_AUDIO_HARDWARE_LOOP.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's context. Continue
only in the allowed paths. Preserve the isolated target, bounded execution,
no-raw-audio rule and fail-closed mute/PA-off behavior. Attempt 008 now has an
operator-confirmed clear/normal speaker-output PASS, while its strict result
remains `FAIL_OR_INCOMPLETE` because of the retained initialization diagnostic.
The offline TX-prearm change is not hardware evidence and needs separate
operator authorization before any run. Treat CALL-010 as
`accepted_for_transition`: the basic input/output endpoints unlock CALL-020,
while real application-level concurrent RX/TX design, explicit DMA
underrun/overrun accounting and a measurable known-chirp/local-loop delay method
remain CALL-010 closure work. Keep exact physical PCB revision and internal
endpoint mapping unknown until verified.
Run every listed validation command and return changed files and exact output.
Do not flash, capture microphones, drive the speaker or issue hardware
commands without a new explicit operator authorization. Do not claim CALL-010
completion, P0-CALL, measured SPL or product acoustics.
```
