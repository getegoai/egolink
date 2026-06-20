"""Small JSONL event store for Ego Link P0 PC Simulator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_recent(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if line.strip():
            rows.append(json.loads(line))
    rows.reverse()
    return rows
