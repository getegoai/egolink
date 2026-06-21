# Safety Companion integration issues

Codex 在集成时发现接口、构建、依赖或硬件问题，按以下格式追加，不要直接修改模型契约：

```text
Issue ID:
Date:
Affected task:
Observed behavior:
Expected behavior:
Relevant files:
Build/test log:
Proposed adapter-side solution:
Contract change requested: yes/no
Reason a contract change may be necessary:
```

Issue ID: M0-INT-001-001
Date: 2026-06-21
Affected task: M0-INT-001 package verification
Observed behavior: the existing repository contract test still expected `safety-companion.contract.v0.1` fields and action names, while the overlay package provides contract `1.0.0`.
Expected behavior: repository-level contract tests should validate the installed package contract without changing package schema semantics.
Relevant files: `quality_tests/model_contract/test_contract_schemas.py`, `shared/contracts/*.schema.json`
Build/test log: `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` failed before the repository test was updated; it now passes 66 tests.
Proposed adapter-side solution: keep the official `shared/contracts/**` files unchanged and update repository tests/adapters to consume contract `1.0.0`.
Contract change requested: no
Reason a contract change may be necessary: not applicable.

Issue ID: M0-INT-001-002
Date: 2026-06-21
Affected task: M0-INT-001 package verification
Observed behavior: generated C threshold header comparison can fail on Windows when text output uses CRLF line endings instead of the committed LF artifact.
Expected behavior: generated threshold headers should be byte-stable across supported development shells.
Relevant files: `model_lab/safety_companion/export/generate_c_header.py`, `model_artifacts/safety_companion/rule_router/0.1.0/include/safety_router_thresholds.h`
Build/test log: `python scripts\verify_safety_companion_m0.py` initially failed at generated header comparison, then passed after the generator forced LF output.
Proposed adapter-side solution: keep threshold values unchanged and make the generator write LF explicitly.
Contract change requested: no
Reason a contract change may be necessary: not applicable.

Issue ID: M0-INT-001-003
Date: 2026-06-21
Affected task: M0-INT-002 PC Simulator adapter
Observed behavior: the existing T023 PC Simulator adapter is a deterministic local mock using the older local contract shape/actions and does not call `RuleRouter` or `build_model_input`.
Expected behavior: M0-INT-002 should route simulator evaluation through `model_lab.safety_companion.RuleRouter` and package feature extraction, then return standard `model_output`.
Relevant files: `pc_simulator/safety_companion.py`, `pc_simulator/app.py`, `model_lab/safety_companion/**`
Build/test log: M0-INT-001 package verification passed; this is a known integration gap for the next task, not a failed package check.
Proposed adapter-side solution: replace the local mock routing path with a thin PC Simulator adapter over the package API and add `/api/safety/evaluate`.
Contract change requested: no
Reason a contract change may be necessary: not applicable.
