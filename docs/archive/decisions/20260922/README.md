---
document_status: historical_archive
archived_at: 2026-09-22
---

# Founder decision alignment source archive

Exact bytes captured before each named ALIGN-STATE-010 edit phase, not a blanket
snapshot of the initial HEAD. Embedded authority/status declarations
in `.md.source` files are historical and non-operative. These snapshots do not
change hardware evidence or authorize runtime, data migration or deletion.

The 2026-09-19 founder decision and 2026-09-22 implementation instruction are
recorded in [ADR-0016](../../../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md).
Use the [migration map](MIGRATION_MAP.md) to find each replacement and SHA-256.
The [manifest](manifest.json) lists all exact sources, including the Master
review checkpoint before restoring still-operative privacy/manufacturing
requirements and the specialist/task decision migrations.
Each entry records `capture_scope`, the comparison commit and whether its bytes
match that commit. Twenty-one snapshots match the recorded Git blobs exactly.
The Master `.review.source` includes this agent's first authority pass;
HW-021's `.source` includes root's earlier WIP metadata edits (`parked`,
`unassigned`, `reviewed_at`) before this agent's native-call clause migration.
Those two entries have no `source_commit`; their snapshot hashes identify the
captured working-tree content. None of the source bytes were rewritten.
Read these sources only for this explicitly named migration or later lineage review.
