---
document_status: proposed_revision
reviewed_at: 2026-09-05
evidence_as_of: 2026-09-04
evidence_method: uploaded_document_review
repository_reverified: false
---
# EgoLink — Active Images and Build Candidates

## Physical nodes: last recorded, not re-probed in this review

| Role | Board | Last recorded flashed image | Last observed port |
|---|---|---|---|
| connectivity_node | Waveshare ESP32-S3-SIM7670G-4G | 0.1.0-fw007-lte-wifi-failover / fw007-e9ca7a4 | COM3 console, 2026-08-16 |
| wearable_node | ESP32-S3-Touch-AMOLED-2.06 | UI-001, restored after CALL-010 run 008 | COM8 USB Serial/JTAG, 2026-09-02 |

Connectivity MAC: `02:00:00:00:00:03`.
Connectivity application SHA-256:
`8F3508C62CA96C54628B3C3FB0A64B5BB14EAF7BBB8188DA54FAEE0739283799`.

Wearable MAC: `02:00:00:00:00:01`.
Wearable application: 659120 bytes; SHA-256:
`11D72868A956E86F7B91D1B9D6008404FBD02B61299D566399DDC90F50A23139`.
Wearable bootloader: 22208 bytes; SHA-256:
`2248730A914CA30FDEC279FE065EB3CB7F1E3C5CBB3F49BE33E6F1C358A9AD63`.
Wearable partition table: 3072 bytes; SHA-256:
`7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`.

Port numbers are dated observations. Identify exact targets before any I/O.
No flash or hardware read was performed by this review.

## Offline candidates reported on 2026-09-04

| Profile | Recorded build path | App bytes (hex) | App partition free | Runtime |
|---|---|---|---|---|
| LOC-021S modem-only | tmp/loc021s_profile_clean_20260904_c/ | 0x5DC90 | 0xA2370 / 63% | NOT_RUN |
| Location legacy default | tmp/loc021s_default_clean_20260904_b/ | 0xDACF0 | 0x25310 / 15% | NOT_RUN for this image |
| CALL-020R default | firmware/audio_loop/build_call020r_fix_default/ | 0x2FB70 | 81% | NOT_RUN |
| CALL-020R owner | firmware/audio_loop/build_call020r_fix_owner/ | 0x45930 | 73% | NOT_RUN |

Application SHA-256, respectively:

```text
LOC-S:        1D9466776D4A388CB4EBE4E853ECFCAD28DDB966460CA3652FB4084099815F5A
LOC-default:  A3D300A60E60031A441826659362B25CB956B534D1C3677795571800BE6B5807
CALL-default: 47E4574BE34AD70507193F56F753E7CD4C3DA97B4E9563EB9FCB56A2A33A519D
CALL-owner:   8EF932C6F5A9E794FBBAEDEB26E9B20B42D85C437DB432940709DA6A5275EA05
```

These source-reported artifacts were not independently located or hashed.
ESP-IDF used: v5.4.2. Recorded host: Windows PowerShell,
`D:\pywork\egolink`; IDF path `C:\Espressif\v5.4.2\esp-idf`.
Do not upgrade the toolchain as part of first runtime convergence.

S selects its own entry and excludes legacy entry; its transport callback
returns no-I/O failure. It does not wire external SOS or IMU ingress. A new
live profile must not masquerade as the original S profile.

## Runtime evidence that can be reused

FW-007 has bounded LTE-to-Wi-Fi takeover evidence, including the 2026-08-16
SIM-removal run. It does not prove Wi-Fi-to-LTE recovery or a persistent queue.
CALL-010 run 007 has operator-confirmed input-stimulus correlation. Run 008 has
operator-confirmed clear/normal output but retains a strict initialization
error. A later output-only fix built successfully and has not run.
UI-001 restore smoke passed status and ask-user rendering after run 008.

Earlier GNSS fix, USB-Free LTE command/ACK, and high-rate QMI8658 windows remain
scoped historical evidence; none is the new integrated candidate's acceptance.

## Server and product state

The latest explicit Dashboard deployment note in the supplied status is
2026-08-11 WEB-003. The current live deployment identity, TLS behavior and
service health were not re-read. September's server candidates are not recorded
as deployed. Never infer live availability from the existence of old records.

P0-LOC = NOT_RUN; P0-CALL = NOT_RUN; P0-SOS = NOT_RUN.
Reported repository check: 1614 pass / 12 skips, not rerun here.

## Promotion rule

Build → bench run → independent-power/representative field → product gate.
For a new candidate record commit, config hash, artifact hash, exact device,
actual route, measurement method, result, limits and recovery identity once.
A prior artifact identity cannot silently be reused after a rebuilding flash.
Long traces and old iterations remain in the
[input archive](../archive/reviews/20260905_input_snapshots/README.md).
