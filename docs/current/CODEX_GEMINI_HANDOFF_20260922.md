---
document_status: coordination
reviewed_at: 2026-09-22
---

# Codex / Gemini work boundary — 2026-09-22

Founder assignment: Codex owns decision/image/backlog alignment, ego-state truth
and contract repair, project management and commits. Gemini owns single-board
recovery/network switching, D2 baseline and FIELD-020.

| Owner | Work and integration boundary |
|---|---|
| Codex | Branch `d2/state-truth-management-20260922`, worktree `D:/pywork/egolink-codex-state-20260922`; ego_state_engine component, PC estimator, ego-state store/API/Web/contracts/tests, current authority/management docs. |
| Gemini | Existing field branch/worktree; camera/spool/recovery/network switching, field profiles/tools and field evidence. Keep using the explicit current candidate manifest; an unflashed Codex source commit is not the running image. |
| Shared seam | `collection_main.c`: Codex changes only ego-state serialization, Gemini owns acquisition/transport/recovery. Merge by hunk and run the relevant regression before binding a new image. `server/collection_store.py` changes are likewise limited by feature. |
| Current facts | Serialize `STATUS.md`, `ACTIVE_BUILD.md` and `BOARD_MATRIX.md` updates by exact image/run; preserve new Gemini evidence. Keep original event time, stable identity, exact ACK and privacy restrictions. |

Do not reset, stash or stage the other worker's changes. Integrate named commits
after reviewing overlap; never copy a whole shared source file over parallel work.
Recovery/route/field evidence remains with the existing P0-CONVERGENCE and
FIELD-020 packets. No hardware operation is authorized by this coordination note.

Codex task: [ALIGN-STATE-010](../tasks/done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md).

## Integration notes from offline acceptance

- Ego-state now uses its own DEVICE record, emitted immediately before the
  ordinary health DEVICE record. Both keep the existing source/envelope/ACK
  contract. Account for the additional frame/envelope in storage, loss and
  throughput budgets when selecting the next field candidate.
- The state view is `egolink.ego_state_view.v0.1` with canonical `state` inside.
  Deploy its backend and Web consumers together when a later task authorizes
  deployment. Legacy frames are visibly adapted; malformed projections retain
  raw storage/ACK but cannot masquerade as valid state. Historical databases
  are revalidated on read, without migration or deletion.
- The production health/envelope/engine/framing offline probe uses synthetic
  hardware snapshots: isolated ego frames are at most 2,079 bytes in its cases;
  camera health is 3,393/3,765 bytes for short/grown counters. These are bounded
  test results, not a universal maximum or real-device proof.
- **Gemini recovery follow-up:** all-source loss counters can make the existing
  health frame alone exceed its 4,000-byte budget: 4,647 bytes for 12 sources,
  5,780 for the 13-source camera profile in the probe. Its serializer returns
  no frame; this pre-existing health/loss-reporting boundary remains unresolved.
  State frames stay independently serializable. Review bounded diagnostics or
  pagination and loss accounting in the recovery packet before field acceptance;
  do not simply raise the persistent-frame limit.
- No native-call readiness/audio fix, sensor-policy rate/power change, local
  Base implementation, real recovery/network experiment or FIELD result is
  included in this Codex delivery. The last reported image remains Boot188.
