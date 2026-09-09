# Status compaction archive — 2026-09-09

This directory preserves the exact pre-compaction contents of
`docs/current/STATUS.md` for provenance. The `.md.source` file is historical
input, not current authority; use `docs/current/STATUS.md` and the router in
`docs/CONTEXT_INDEX.md` for current work.

| Source | Bytes | SHA-256 |
|---|---:|---|
| `STATUS_BEFORE_COMPACTION_20260909.md.source` | 346488 | `BFE5972E0576F942F956EB55BCF80EB3244E44C31109300A99C62D14D85E39BD` |

Migration reason: the old file had accumulated a chronological project log and
an embedded 2026-06-27 snapshot whose `current` hardware, task and credential
statements conflicted with later evidence. The complete source remains here;
the authoritative file now contains only current outcomes, blockers, decisions
and immediate execution order as required by `docs/AGENTS.md`.
