"""Local ``did:key`` identities (Ed25519). Demo key handling, not production key management."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED25519_MULTICODEC = b"\xed\x01"
_DID_PREFIX = "did:key:z"


def b58encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    digits = ""
    while number:
        number, remainder = divmod(number, 58)
        digits = _ALPHABET[remainder] + digits
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + digits


def b58decode(text: str) -> bytes:
    number = 0
    for char in text:
        index = _ALPHABET.find(char)
        if index < 0:
            raise ValueError("Invalid base58 character")
        number = number * 58 + index
    body = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\0" * (len(text) - len(text.lstrip("1"))) + body


def did_from_public_key(public_key: bytes) -> str:
    if len(public_key) != 32:
        raise ValueError("An Ed25519 public key has 32 bytes")
    return _DID_PREFIX + b58encode(_ED25519_MULTICODEC + public_key)


def public_key_from_did(did: str) -> bytes:
    if not did.startswith(_DID_PREFIX):
        raise ValueError("Only did:key identities with a base58btc key are supported")
    raw = b58decode(did[len(_DID_PREFIX) :])
    if raw[:2] != _ED25519_MULTICODEC or len(raw) != 34:
        raise ValueError("The did:key does not hold an Ed25519 public key")
    return raw[2:]


def verify_signature(did: str, data: bytes, signature: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key_from_did(did)).verify(signature, data)
    except (InvalidSignature, ValueError):
        return False
    return True


class AgentKey:
    """An agent's signing key and the ``did:key`` derived from it."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key
        public = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.did = did_from_public_key(public)

    @classmethod
    def generate(cls) -> "AgentKey":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, seed: bytes) -> "AgentKey":
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    @classmethod
    def load_or_create(cls, path: str | os.PathLike[str]) -> "AgentKey":
        """Read the hex seed at ``path``; create the file (mode 600) if it is missing."""
        target = Path(path)
        if target.exists():
            return cls.from_seed(bytes.fromhex(target.read_text(encoding="ascii").strip()))
        key = cls.generate()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(key.seed.hex() + "\n", encoding="ascii")
        try:
            target.chmod(0o600)
        except OSError:
            pass
        return key

    @property
    def seed(self) -> bytes:
        return self._private_key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        )

    def sign(self, data: bytes) -> bytes:
        return self._private_key.sign(data)

    def __repr__(self) -> str:  # never print key material
        return f"AgentKey({self.did})"
