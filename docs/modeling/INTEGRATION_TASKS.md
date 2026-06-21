# Safety Companion M0 Integration Tasks

## T022 Scope

Integrate the model collaboration idea into Ego Link as a contract-first M0
baseline. This task creates stable boundaries, not a real model runtime.

## Requirements

1. Add shared JSON contracts for sensor frames, safety events, model inputs,
   model outputs, and base commands.
2. Add contract tests that verify the schema files exist, are valid JSON, use
   the same contract version, and keep the first required fields stable.
3. Document the ownership split between model package code and Codex integration
   code.
4. Update project status so the next implementation task can map current
   `sos_pressed`, `wake_detected`, `location_report`, `sensor_sample`, and
   device-risk events into `model_input`.

## Not In T022

- No model training.
- No neural network inference.
- No ESP-DL, ESP-SR, or TFLite Micro integration.
- No changes to firmware runtime behavior.
- No new production dependencies.

## Next Suggested Task

T023 should add a PC-side adapter that converts recent PC Simulator events into
`model_input` and returns a deterministic mock `model_output`. That gives us the
first end-to-end safety companion loop while real MotionNet and ContextRouter
work remains outside the firmware path.

