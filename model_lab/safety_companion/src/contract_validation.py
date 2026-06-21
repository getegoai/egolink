"""Small dependency-free validator for the JSON Schema subset used by M0.

This is deliberately not a general JSON Schema implementation. It supports the
keywords used in ``shared/contracts`` so the package can run on a clean Python
installation without downloading dependencies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class ContractValidationError(ValueError):
    """Raised when a contract instance is invalid."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = list(issues)
        super().__init__("; ".join(str(issue) for issue in self.issues))


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_schema(schema_name: str, repo_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root else _find_repo_root()
    path = root / "shared" / "contracts" / schema_name
    if not path.is_file():
        raise FileNotFoundError(f"Contract schema not found: {path}")
    return load_json(path)


def validate_file(instance_path: str | Path, schema_path: str | Path) -> None:
    instance = load_json(instance_path)
    schema = load_json(schema_path)
    validate_instance(instance, schema)


def validate_instance(instance: Any, schema: dict[str, Any]) -> None:
    issues: list[ValidationIssue] = []
    _validate(instance, schema, "$", issues)
    if issues:
        raise ContractValidationError(issues)


def is_valid(instance: Any, schema: dict[str, Any]) -> bool:
    try:
        validate_instance(instance, schema)
    except ContractValidationError:
        return False
    return True


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "shared" / "contracts").is_dir():
            return parent
    raise RuntimeError("Could not locate repository root containing shared/contracts")


def _validate(value: Any, schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    if "const" in schema and value != schema["const"]:
        issues.append(ValidationIssue(path, f"must equal {schema['const']!r}"))
        return

    if "enum" in schema and value not in schema["enum"]:
        issues.append(ValidationIssue(path, f"must be one of {schema['enum']!r}"))
        return

    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        issues.append(ValidationIssue(path, f"expected type {expected_type!r}, got {type(value).__name__}"))
        return

    if value is None:
        return

    if isinstance(value, dict):
        _validate_object(value, schema, path, issues)
    elif isinstance(value, list):
        _validate_array(value, schema, path, issues)
    elif isinstance(value, str):
        _validate_string(value, schema, path, issues)
    elif _is_number(value):
        _validate_number(value, schema, path, issues)


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    expected_types = [expected] if isinstance(expected, str) else expected
    return any(_matches_single_type(value, item) for item in expected_types)


def _matches_single_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return _is_number(value)
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_object(value: dict[str, Any], schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    required = schema.get("required", [])
    for key in required:
        if key not in value:
            issues.append(ValidationIssue(path, f"missing required property {key!r}"))

    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, child in value.items():
        child_path = f"{path}.{key}"
        if key in properties:
            _validate(child, properties[key], child_path, issues)
        elif additional is False:
            issues.append(ValidationIssue(child_path, "additional property is not allowed"))
        elif isinstance(additional, dict):
            _validate(child, additional, child_path, issues)


def _validate_array(value: list[Any], schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    if min_items is not None and len(value) < min_items:
        issues.append(ValidationIssue(path, f"must contain at least {min_items} items"))
    if max_items is not None and len(value) > max_items:
        issues.append(ValidationIssue(path, f"must contain at most {max_items} items"))
    if schema.get("uniqueItems"):
        seen: set[str] = set()
        for item in value:
            marker = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if marker in seen:
                issues.append(ValidationIssue(path, "items must be unique"))
                break
            seen.add(marker)
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            _validate(item, item_schema, f"{path}[{index}]", issues)


def _validate_string(value: str, schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    min_length = schema.get("minLength")
    max_length = schema.get("maxLength")
    pattern = schema.get("pattern")
    if min_length is not None and len(value) < min_length:
        issues.append(ValidationIssue(path, f"length must be at least {min_length}"))
    if max_length is not None and len(value) > max_length:
        issues.append(ValidationIssue(path, f"length must be at most {max_length}"))
    if pattern is not None and re.search(pattern, value) is None:
        issues.append(ValidationIssue(path, f"must match pattern {pattern!r}"))


def _validate_number(value: int | float, schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    exclusive_minimum = schema.get("exclusiveMinimum")
    exclusive_maximum = schema.get("exclusiveMaximum")
    if minimum is not None and value < minimum:
        issues.append(ValidationIssue(path, f"must be >= {minimum}"))
    if maximum is not None and value > maximum:
        issues.append(ValidationIssue(path, f"must be <= {maximum}"))
    if exclusive_minimum is not None and value <= exclusive_minimum:
        issues.append(ValidationIssue(path, f"must be > {exclusive_minimum}"))
    if exclusive_maximum is not None and value >= exclusive_maximum:
        issues.append(ValidationIssue(path, f"must be < {exclusive_maximum}"))
