# Ego Link P0

Ego Link P0 is the first engineering-alpha slice of an AI-assisted active
safety locator. The current product-like loop is:

```text
4G device -> LTE -> Message Hub -> Web Dashboard
          -> bounded field evidence -> D2/D5 location data flywheel
```

The current release target is **v0.1.0 Engineering Alpha**. It is usable as an
engineering field-test product, but it is not a mass-production claim.

## What Works Now

- 4G board periodically uploads location, LTE/cell, IMU status, power, and raw
  POST counters to the Message Hub.
- The Web Dashboard shows live device state, location estimate, local no-key
  map/trajectory evidence, field-test results, and D5 data-flywheel status.
- D1 outdoor field observations can be summarized into bounded evidence without
  exposing raw coordinates or cell-ID lists in committed summaries.
- D2/D5 offline tooling exists for location accuracy baselines, review packets,
  dataset manifest gates, and field-evidence intake.
- The AMOLED board is a sidecar display/interaction surface for field status.

## Non-Claims

- No production location-accuracy claim until a D2 reference-point baseline
  reports median error, fix rate, and TTFF.
- No real calling, SMS, emergency dispatch, or contact-notification claim.
- No product battery-life claim until long-duration power evidence is accepted.
- No model-performance claim. Tiny Safety assets are retained as engineering
  scaffolding; the active model mainline is location accuracy.
- No training use of private field data without explicit review, privacy,
  quality, split, and founder approval gates.

## Product-Like Local Run

Start the local Message Hub and Web Dashboard:

```powershell
python scripts\run_message_hub.py --port 8790
```

Then open:

```text
http://127.0.0.1:8790
```

The older PC simulator remains useful for mock safety/UI exercises, but it is
not the primary product-like D1/D2/D5 dashboard path:

```powershell
python pc_simulator\app.py --port 8787
```

For a live field session, use the D1 field observer against the configured hub
and device:

```powershell
python scripts\observe_d1_field_run.py --help
```

After a field run, summarize real D1 samples into D5 field evidence:

```powershell
python scripts\summarize_location_field_evidence.py --samples reports\d1_field_observation\<run-id>\d1_field_samples.jsonl
```

When a FIELD-003 reference manifest and test-run export are available, run the
D2 -> D5 location pipeline:

```powershell
python scripts\run_location_d2_d5_pipeline.py --input <test_run_export.json> --manifest <field_manifest.json>
```

## Development Flow

Use GitHub Flow:

1. `main` must stay buildable, runnable, and releaseable.
2. Work happens on short branches such as `egolink-p0` or
   `task/<TASK-ID>-short-name`.
3. Merge only after validation and a clear release/readiness statement.
4. Tag demo or engineering-alpha checkpoints with `v0.x.y`.

Core context:

- North star: `docs/product/NORTH_STAR.md`
- Context router: `docs/CONTEXT_INDEX.md`
- Current state: `docs/current/STATUS.md`
- Active build: `docs/current/ACTIVE_BUILD.md`
- Git/task flow: `docs/development/GIT_FLOW.md`
- P0 walking skeleton: `docs/development/DEV_FLOW.md`

## Validation

For context-only changes:

```powershell
python scripts\context_lint.py
```

For behavior or release changes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```
