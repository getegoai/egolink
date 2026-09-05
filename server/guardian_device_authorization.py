"""Fail-closed Guardian-to-device authorization for the P0 location view.

The configuration stores only SHA-256 token digests. Device-ingest credentials
remain owned by Message Hub and are deliberately not accepted here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTRACT_VERSION = "egolink.guardian_device_bindings.v0.1"
MAX_CONFIG_BYTES = 64 * 1024
MAX_BINDINGS = 1024
MAX_DEVICES_PER_GUARDIAN = 64
MIN_TOKEN_BYTES = 16
MAX_TOKEN_BYTES = 256
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GuardianAuthorizationConfigError(ValueError):
    """Raised when a binding file is unsafe or ambiguous."""


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GuardianAuthorizationConfigError(
                "guardian binding JSON contains a duplicate member"
            )
        result[key] = value
    return result


@dataclass(frozen=True)
class GuardianAuthorizationDecision:
    status: str
    guardian_id: str | None = None

    @property
    def authorized(self) -> bool:
        return self.status == "authorized"


@dataclass(frozen=True)
class _Binding:
    guardian_id: str
    token_sha256: str = field(repr=False)
    device_ids: frozenset[str]


def _exact_object(
    value: Any,
    *,
    required: frozenset[str],
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != required:
        raise GuardianAuthorizationConfigError(
            f"{name} must contain exactly: {', '.join(sorted(required))}"
        )
    return value


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise GuardianAuthorizationConfigError(
            f"{name} must be a 1-128 character safe identifier"
        )
    return value


class GuardianDeviceAuthorizer:
    """Immutable, thread-safe authorization table with no plaintext tokens."""

    def __init__(self, document: Mapping[str, Any]):
        root = _exact_object(
            document,
            required=frozenset({"contract_version", "bindings"}),
            name="guardian binding document",
        )
        if root["contract_version"] != CONTRACT_VERSION:
            raise GuardianAuthorizationConfigError(
                "guardian binding contract_version is unsupported"
            )
        raw_bindings = root["bindings"]
        if (
            not isinstance(raw_bindings, list)
            or not raw_bindings
            or len(raw_bindings) > MAX_BINDINGS
        ):
            raise GuardianAuthorizationConfigError(
                f"bindings must contain 1-{MAX_BINDINGS} entries"
            )

        bindings: list[_Binding] = []
        seen_guardians: set[str] = set()
        seen_hashes: set[str] = set()
        for index, value in enumerate(raw_bindings):
            raw = _exact_object(
                value,
                required=frozenset({"guardian_id", "token_sha256", "device_ids"}),
                name=f"bindings[{index}]",
            )
            guardian_id = _safe_id(raw["guardian_id"], f"bindings[{index}].guardian_id")
            token_sha256 = raw["token_sha256"]
            if not isinstance(token_sha256, str) or _SHA256.fullmatch(token_sha256) is None:
                raise GuardianAuthorizationConfigError(
                    f"bindings[{index}].token_sha256 must be 64 lowercase hex characters"
                )
            device_values = raw["device_ids"]
            if (
                not isinstance(device_values, list)
                or not device_values
                or len(device_values) > MAX_DEVICES_PER_GUARDIAN
            ):
                raise GuardianAuthorizationConfigError(
                    f"bindings[{index}].device_ids must contain "
                    f"1-{MAX_DEVICES_PER_GUARDIAN} entries"
                )
            device_ids = [
                _safe_id(item, f"bindings[{index}].device_ids")
                for item in device_values
            ]
            if len(set(device_ids)) != len(device_ids):
                raise GuardianAuthorizationConfigError(
                    f"bindings[{index}].device_ids contains a duplicate"
                )
            if guardian_id in seen_guardians:
                raise GuardianAuthorizationConfigError("guardian_id is duplicated")
            if token_sha256 in seen_hashes:
                raise GuardianAuthorizationConfigError("token_sha256 is duplicated")
            seen_guardians.add(guardian_id)
            seen_hashes.add(token_sha256)
            bindings.append(
                _Binding(
                    guardian_id=guardian_id,
                    token_sha256=token_sha256,
                    device_ids=frozenset(device_ids),
                )
            )
        self._bindings = tuple(bindings)

    @classmethod
    def from_file(cls, path: Path) -> "GuardianDeviceAuthorizer":
        if not isinstance(path, Path):
            raise GuardianAuthorizationConfigError("binding path must be a Path")
        try:
            size = path.stat().st_size
        except OSError as error:
            raise GuardianAuthorizationConfigError(
                "guardian binding file is unavailable"
            ) from error
        if size <= 0 or size > MAX_CONFIG_BYTES:
            raise GuardianAuthorizationConfigError(
                f"guardian binding file must be 1-{MAX_CONFIG_BYTES} bytes"
            )
        try:
            raw = path.read_bytes()
            if len(raw) <= 0 or len(raw) > MAX_CONFIG_BYTES:
                raise GuardianAuthorizationConfigError(
                    f"guardian binding file must be 1-{MAX_CONFIG_BYTES} bytes"
                )
            document = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_members
            )
        except GuardianAuthorizationConfigError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GuardianAuthorizationConfigError(
                "guardian binding file is not valid UTF-8 JSON"
            ) from error
        return cls(document)

    def authorize(
        self,
        authorization_header: str | None,
        device_id: str,
    ) -> GuardianAuthorizationDecision:
        """Authenticate first, then decide binding without exposing identities."""

        if not isinstance(device_id, str) or _SAFE_ID.fullmatch(device_id) is None:
            return GuardianAuthorizationDecision("forbidden")
        token = self._bearer_token(authorization_header)
        if token is None:
            return GuardianAuthorizationDecision("unauthenticated")
        digest = hashlib.sha256(token).hexdigest()
        matched: _Binding | None = None
        for binding in self._bindings:
            if hmac.compare_digest(digest, binding.token_sha256):
                matched = binding
        token = b""
        if matched is None:
            return GuardianAuthorizationDecision("unauthenticated")
        if device_id not in matched.device_ids:
            return GuardianAuthorizationDecision("forbidden")
        return GuardianAuthorizationDecision(
            "authorized", guardian_id=matched.guardian_id
        )

    @staticmethod
    def _bearer_token(header: str | None) -> bytes | None:
        if not isinstance(header, str) or not header.startswith("Bearer "):
            return None
        value = header[7:]
        try:
            token = value.encode("ascii")
        except UnicodeEncodeError:
            return None
        if (
            len(token) < MIN_TOKEN_BYTES
            or len(token) > MAX_TOKEN_BYTES
            or any(byte <= 0x20 or byte >= 0x7F for byte in token)
        ):
            return None
        return token


def token_sha256(token: str) -> str:
    """Provisioning helper; returns a digest and never persists the token."""

    encoded = GuardianDeviceAuthorizer._bearer_token(f"Bearer {token}")
    if encoded is None:
        raise GuardianAuthorizationConfigError(
            f"token must be {MIN_TOKEN_BYTES}-{MAX_TOKEN_BYTES} visible ASCII bytes"
        )
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CONTRACT_VERSION",
    "GuardianAuthorizationConfigError",
    "GuardianAuthorizationDecision",
    "GuardianDeviceAuthorizer",
    "token_sha256",
]
