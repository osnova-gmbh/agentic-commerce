"""Ed25519 compact JWS for the optional Affinidi identity slice."""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Mapping

from ..canonical import canonical_bytes
from ..keys import AgentKey, public_key_from_did, verify_signature


class IdentityError(ValueError):
    """Invalid identity proof; messages deliberately omit proof contents."""


def verification_method(did: str) -> str:
    public_key_from_did(did)
    return did + "#" + did.rsplit(":", 1)[-1]


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise IdentityError("Invalid compact JWS encoding")
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as error:
        raise IdentityError("Invalid compact JWS encoding") from error


def _object(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise IdentityError("Duplicate JWS claim")
            result[key] = value
        return result

    try:
        result = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError) as error:
        raise IdentityError("Invalid compact JWS JSON") from error
    if not isinstance(result, dict):
        raise IdentityError("JWS content must be a JSON object")
    return result


def sign_jws(key: AgentKey, payload: Mapping) -> str:
    """Sign a standard compact JWS; the key never leaves AgentKey."""
    header = {"alg": "EdDSA", "kid": verification_method(key.did), "typ": "JWT"}
    signing_input = _encode(canonical_bytes(header)) + "." + _encode(canonical_bytes(dict(payload)))
    return signing_input + "." + _encode(key.sign(signing_input.encode("ascii")))


def verify_jws(token: str, expected_did: str, *, expected_claims: Mapping | None = None,
               now: float | None = None, max_age_seconds: int = 300) -> dict:
    """Verify a pinned identity, signature, validity window and expected request claims."""
    if not isinstance(token, str) or len(token) > 32768:
        raise IdentityError("Invalid compact JWS")
    parts = token.split(".")
    if len(parts) != 3:
        raise IdentityError("Invalid compact JWS")
    header, payload = _object(_decode(parts[0])), _object(_decode(parts[1]))
    method = verification_method(expected_did)
    if header.get("alg") != "EdDSA" or header.get("kid") != method:
        raise IdentityError("Unexpected JWS signer or algorithm")
    if header.get("crit") or "b64" in header:
        raise IdentityError("Unsupported JWS header extension")
    if not verify_signature(expected_did, ".".join(parts[:2]).encode("ascii"), _decode(parts[2])):
        raise IdentityError("Invalid JWS signature")
    issued, expires = payload.get("iat"), payload.get("exp")
    current = time.time() if now is None else now
    if type(issued) is not int or type(expires) is not int:
        raise IdentityError("JWS must have integer issued and expiry times")
    if issued > current + 30 or expires <= current or expires <= issued:
        raise IdentityError("JWS is expired or not yet valid")
    if current - issued > max_age_seconds or expires - issued > max_age_seconds:
        raise IdentityError("JWS validity window is too long")
    for name, expected in (expected_claims or {}).items():
        actual = payload.get(name)
        if type(actual) is not type(expected) or actual != expected:
            raise IdentityError("JWS request binding mismatch")
    return payload


def _validate_quote(payload: Mapping) -> None:
    for name in ("sku", "nonce"):
        if not isinstance(payload.get(name), str) or not payload[name]:
            raise IdentityError("Quote requires SKU and request nonce")
    if type(payload.get("quantity")) is not int or payload["quantity"] <= 0:
        raise IdentityError("Quote quantity must be a positive integer")
    if type(payload.get("amount_minor")) is not int or payload["amount_minor"] < 0:
        raise IdentityError("Quote amount must be nonnegative integer minor units")
    if not isinstance(payload.get("currency"), str) or not re.fullmatch(r"[A-Z]{3}", payload["currency"]):
        raise IdentityError("Quote currency must be a three-letter code")


def sign_quote(key: AgentKey, *, sku: str, quantity: int, amount_minor: int,
               currency: str, nonce: str, now: float | None = None, ttl_seconds: int = 300) -> str:
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
        raise IdentityError("Quote lifetime must be between 1 and 300 seconds")
    issued = int(time.time() if now is None else now)
    payload = {"seller_did": key.did, "sku": sku, "quantity": quantity,
               "amount_minor": amount_minor, "currency": currency, "nonce": nonce,
               "iat": issued, "exp": issued + ttl_seconds}
    _validate_quote(payload)
    return sign_jws(key, payload)


def verify_quote(token: str, expected_did: str, *, sku: str, quantity: int, nonce: str,
                 amount_minor: int | None = None, currency: str | None = None,
                 now: float | None = None) -> dict:
    expected = {"seller_did": expected_did, "sku": sku, "quantity": quantity, "nonce": nonce}
    if amount_minor is not None:
        expected["amount_minor"] = amount_minor
    if currency is not None:
        expected["currency"] = currency
    result = verify_jws(token, expected_did, expected_claims=expected, now=now)
    _validate_quote(result)
    return result
