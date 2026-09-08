---
document_status: proposed_task_packet
created_at: 2026-09-05
status: ready_for_repository_reconciliation
owner: codex_integrator
runtime_authorization: not_granted_by_this_packet
---
# P0-CONVERGENCE-20260905 — Deliver a live Location slice

## Product outcome

On an identified connectivity node, a genuine GNSS/Cell observation changes
device-owned Location state and reaches an authorized Guardian via verified
secure transport. Guardian displays correct source/age/uncertainty and never
claims delivered, current or precise state from missing evidence.

This is the first runtime-convergence task. It does not claim P0-LOC, implement
all concurrent product ingress, or re-create the entire architecture.
The parallel CALL work is a bounded supporting investigation, not its dependency.

## Step 0 — reconcile the real workspace, then implement

Read root/module AGENTS, `docs/CONTEXT_INDEX.md`, product charter, NORTH_STAR,
FIRST_LAUNCH_EXECUTION, ADR-0011/0012/0013, BOARD_MATRIX, current active packets
and source owners. Check branch/HEAD/worktree before any edit; do not overwrite
uncommitted work. Compare uploaded-source hashes to actual files.

Merge the revision candidates with newer facts and allocate the ADR number.
Update absent-from-this-package authorities only after reading their full text.
The docs/AGENTS candidate must never overwrite root AGENTS.
The short routing/document update is the start of this packet, not completion.

## Step 1 — trace one executable path

Inspect actual entry/config selection → UART/modem owner → observation mapper
→ Location reducer/policy → emitter/outbox → secure connector → server ingest
→ bound Guardian projection. Produce a short seam checklist in the task result.
Choose the fewest unconnected seams. Reuse Q/R and the proven adapters where
appropriate; do not add a new generic owner, factory or adapter framework.

Specific decisions to resolve in code review:
- Current-boot single-source input avoids a general cross-source WAL dependency.
- Confirm whether zero/missing HDOP is being confused with receiver no-fix.
- Separate local state progress from failed outbound persistence.
- The actual transport must preserve exact complete response bytes and verified
  TLS peer identity, or remain unavailable; do not silently fall back to HTTP.
- Keep the existing field-test storage bounded and labelled; no endurance claim.

## Step 2 — implement one named engineering profile

Add/select a narrow live profile using existing build tooling. Keep the normal
legacy image unchanged. The profile must have a real application entry, one
modem owner, one state loop and one delivery owner; a fake TRANSPORT_FAILED
callback is not an implementation of live delivery.

Configuration declares exact board/pins/transport, run limits, GNSS work budget,
upload cadence and storage-write budget. Candidate secrets live only in the
existing ignored credential mechanism. No unrequested dependency/toolchain bump.

The profile emits/records boot identity, source event time, seq, source state,
last trusted reference, age/quality/uncertainty, current persistence status,
last attempted delivery and matched server acknowledgement. Aggregate counters
are enough; avoid sensitive raw-data logging by default.

A failed GNSS attempt returns promptly with no-fix/error provenance and aged
prior evidence. A stale point never becomes a fresh fix. A full queue reports
its policy and counters. A new claim of cross-boot recovery requires its own
persisted identity/checkpoint tests.

## Step 3 — executable local regression and actual builds

Before hardware, run the C/host behavioral tests that really execute this path,
not only file-text assertions. Include finite event time, valid/no-fix/error,
missing quality, stale input, queue-full/storage-error, wrong/malformed ACK,
response truncation, cancellation, owner exclusivity and graceful shutdown.
Inspect every skip touching the new path; run in an appropriate local native
runner or keep the affected capability unverified. Keep unaffected legacy tests.

Build both legacy default and the selected live profile with the pinned IDF.
Record source/config/image identity and show only the intended entry is linked.
Run repository context lint and diff check; full regression at the integrated
candidate boundary. Do not claim a test executed when only its source matched.

## Step 4 — bounded experiment scope

Use an existing unexpired authorization only if it covers this exact operation.
Otherwise return one combined scope for the operator, rather than repeated
per-command approval requests. No live I/O is authorized by this task text.

The scope must contain: exact node identity, image and recovery hashes, ports
reidentified at run time, endpoint and identity-verification rules, network/SIM
route, data/capture policy, duration/attempt/write/traffic limits, participants,
stop conditions and physical placement. Never test as someone's safety lifeline.

Suggested first run design, to approve and parameterize from source limits:
a short owner smoke, then a bounded live Location session with several cached
state queries, one normal source update and no-fix/error observation if the
environment produces it. Do not force a GNSS-success claim indoors.
Server/Guardian must bind the same device/run/image/observation identity.
No microphone/camera or non-test Guardian notification belongs to this run.

Stop on wrong device/image, unexpected reset/brownout/thermal issue, possible
concurrent modem owner, runaway writes/traffic, bad auth/TLS or privacy-policy
violation. Preserve evidence; restore the exact known image only within scope.

## Acceptance

| Layer | Required output |
|---|---|
| Code delivery | Concrete selected runtime, real transport implementation, executable tests, builds and migration |
| First live proof | Real device state reaches authorized Guardian on the verified route; age/source/failure correctly shown |
| Failure truth | No fake fix/ACK; incomplete responses retained for retry; cancellation bounded; local state degradation visible |
| Recovery | Candidate reset/retry scope accurately stated; unsupported power-loss/replay remains unclaimed |
| Handoff | One concise result naming user-visible change, source/config/image, measured evidence, remaining blocker and next action |

A successful build can complete the code-delivery portion, but not the live
portion. Mark `runtime_waiting_authorization` where appropriate. Do not mark the
entire packet or product gate PASS while the only evidence is offline.

## Parallel CALL slice: separate writer and clear stop point

Reuse CALL-010 endpoints and CALL-020 A-R. Close real authentication, concrete
TLS/route, Guardian endpoint, RESULT/post-stop telemetry and heap/stack counters.
Demonstrate both acoustic directions first; then repeat on a source-bound verified
SIM/LTE path. Existing longer/repeated CALL-020 campaign requirements remain.

Compare the existing custom bridge against a pinned maintained embedded RTC
candidate using exact board/codec/IDF compatibility, license, memory, transport
and measured integration effort. Do not adopt a new stack solely from a README.
A short embedded bearer probe may start before final HW-022. It must use the
same single modem ownership design; final CALL-021 still waits for product
hardware. Freeze additional generic PC-bridge layers unless a real run needs them.

## After the live slice

Integrate SOS physical input, distinguish recognized/stored/server-received/
terminal-noticed/human-acknowledged, and test full/storage failure and missing
GNSS. Join pending-event recovery and independently powered carry tests.
Start power/RF/Guardian-reachability measurements early, then use representative
campaigns before promoting product gates.

## Do not expand this task into

Universal sensor event sourcing, a new training platform, camera awareness,
production BOM freeze, full repository rewrite, arbitrary API churn, new visual
Dashboard report panels, or purchasing a new chip to avoid diagnosis.
