# Quality Tests Module Instructions

- Read root `AGENTS.md`, `docs/CONTEXT_INDEX.md`, and the documents or modules covered by the test before editing tests.
- Tests should protect documented contracts and current behavior.
- Do not weaken assertions, delete coverage, or hide errors to make validation pass.
- Prefer focused tests for context-only changes; run full `scripts/verify.ps1` when behavior may be affected.
