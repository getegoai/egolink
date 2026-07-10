# PC Simulator Module Instructions

- Read root `AGENTS.md`, `docs/CONTEXT_INDEX.md`, `docs/architecture/SYSTEM_OVERVIEW.md`, and `shared/contracts/` before simulator or bridge work.
- PC Simulator is a development bridge, observer, recorder, and replay tool. It is not formal Ego Base.
- Do not hardcode COM port numbers in product-facing discovery paths.
- Keep runtime logs and recordings under `pc_simulator/runtime/`; do not treat runtime data as default context.
- Protocol changes must be coordinated with `shared/contracts/` and the active task.
