# Safety Companion M0 Integration Report

## Current Integration

T023 connects the M0 contract layer to PC Simulator with a deterministic mock
router. It does not introduce a trained model or device-side inference runtime.

Implemented pieces:

- `pc_simulator/safety_companion.py` builds a contract-compatible
  `model_input` from recent PC Simulator events and device state.
- The same module returns a deterministic mock `model_output`.
- `pc_simulator/app.py` includes `safety_companion` in `/api/state`.
- Dashboard shows risk type, risk score, recommended action, and reason codes.

## Covered Rules

- `sos_pressed` -> `manual_sos`, `escalate_emergency`.
- GNSS `location_report` with `fix=false` -> `device_risk`, `upload_summary`,
  reason `gnss_no_fix`.
- Low battery `sensor_sample` -> `device_risk`, `local_reminder`.
- `wake_detected` -> `none`, `ask_user`, without emergency escalation.
- No risk signal -> `none`, `ignore`.

## Verification

```powershell
python -m unittest quality_tests.test_safety_companion -v
python -m unittest quality_tests.test_pc_simulator -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Latest verified result: `scripts\verify.ps1` passed with 54 tests.

## Hardware Status

No new hardware behavior was added in T023. The live Dashboard API was refreshed
and returned:

```json
{
  "active_event": "location_report",
  "safety_risk": "device_risk",
  "safety_action": "upload_summary",
  "reasons": "gnss_no_fix"
}
```

This confirms the PC-side adapter loop, not model accuracy.

## Next Integration Step

T024 should publish Safety Companion recommendations as explicit PC Simulator
events or commands, so the event stream can show when the router recommends
asking the user, uploading a summary, or escalating.

