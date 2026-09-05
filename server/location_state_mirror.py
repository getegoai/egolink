"""JSON-Schema oracle around the stdlib Location State runtime core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from server.location_state_runtime import *  # noqa: F401,F403
from server.location_state_runtime import (
    LocationStateRuntimeMirror,
    LocationStateValidationError,
    REPOSITORY_ROOT,
)


DEFAULT_LOCATION_STATE_SCHEMA = (
    REPOSITORY_ROOT / "shared" / "contracts" / "location_engine_v0.schema.json"
)
DEFAULT_LOCATION_ENVELOPE_SCHEMA = (
    REPOSITORY_ROOT / "shared" / "contracts" / "location_state_envelope_v0.schema.json"
)


class LocationStateMirror(LocationStateRuntimeMirror):
    """Development/schema-oracle facade preserving the original public API."""

    def __init__(
        self,
        policy_config=None,
        *,
        location_state_schema_path: str | Path = DEFAULT_LOCATION_STATE_SCHEMA,
        location_envelope_schema_path: str | Path = DEFAULT_LOCATION_ENVELOPE_SCHEMA,
    ) -> None:
        try:
            state_schema = json.loads(Path(location_state_schema_path).read_text("utf-8"))
            envelope_schema = json.loads(
                Path(location_envelope_schema_path).read_text("utf-8")
            )
            Draft202012Validator.check_schema(state_schema)
            Draft202012Validator.check_schema(envelope_schema)
            registry = Registry().with_resource(
                state_schema["$id"], Resource.from_contents(state_schema)
            )
        except (OSError, json.JSONDecodeError, SchemaError) as exc:
            raise LocationStateValidationError(
                "unable to load the accepted Location Engine contracts"
            ) from exc
        self._state_validator = Draft202012Validator(state_schema)
        self._envelope_validator = Draft202012Validator(
            envelope_schema, registry=registry
        )
        super().__init__(policy_config)

    @staticmethod
    def _raise_first_contract_error(validator, value: Mapping[str, Any], name: str) -> None:
        errors = sorted(
            validator.iter_errors(dict(value)),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            error = errors[0]
            path = ".".join(str(part) for part in error.absolute_path) or "<root>"
            raise LocationStateValidationError(
                f"{name} contract violation at {path} ({error.validator})"
            )

    def _validate_envelope_contract(self, envelope: Mapping[str, Any]) -> None:
        self._raise_first_contract_error(
            self._envelope_validator, envelope, "location state envelope"
        )
        super()._validate_envelope_contract(envelope)

    def _validate_state_contract(self, state: Mapping[str, Any]) -> None:
        self._raise_first_contract_error(
            self._state_validator, state, "location_state"
        )
        super()._validate_state_contract(state)
