"""Replay sensor frames or model inputs through the M0 baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from .baseline_router import RuleRouter
from .feature_extractor import build_model_input


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield value


def replay_model_inputs(inputs: Iterable[dict[str, Any]], router: RuleRouter | None = None) -> list[dict[str, Any]]:
    engine = router or RuleRouter()
    return [engine.evaluate(item) for item in inputs]


def replay_sensor_frames(frames: Iterable[dict[str, Any]], router: RuleRouter | None = None) -> list[dict[str, Any]]:
    engine = router or RuleRouter()
    return [engine.evaluate(build_model_input(frame)) for frame in frames]


def write_jsonl(path: str | Path, values: Iterable[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
