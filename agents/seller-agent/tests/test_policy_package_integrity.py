"""Release pins reject altered resource bytes before selecting policy authority."""

from __future__ import annotations

import json
from importlib.resources import files
from io import BytesIO

import pytest
from cogit_agent_sdk.types import AgentDescriptor

from seller_agent_setup import policy
from seller_agent_setup.errors import SetupError


class Resource:
    def __init__(self, encoded: bytes | None) -> None:
        self.encoded = encoded

    def open(self, mode: str) -> BytesIO:
        assert mode == "rb"
        if self.encoded is None:
            raise FileNotFoundError("fixture resource missing")
        return BytesIO(self.encoded)


class Package:
    def __init__(self, values: dict[str, bytes | None]) -> None:
        self.values = values

    def joinpath(self, name: str) -> Resource:
        return Resource(self.values[name])


def descriptor() -> AgentDescriptor:
    return AgentDescriptor(name="pin-test", version="1.0.0", description="fixture")


@pytest.mark.parametrize(
    "resource_name", ["runtime-policy-package.json", "universal-policy-package.json"]
)
@pytest.mark.parametrize(
    "failure", ["missing", "malformed", "oversized", "digest", "export", "nested"]
)
def test_altered_resources_cannot_select_authority(
    monkeypatch: pytest.MonkeyPatch, resource_name: str, failure: str
) -> None:
    root = files("seller_agent_setup")
    values: dict[str, bytes | None] = {
        name: root.joinpath(name).read_bytes()
        for name in ("runtime-policy-package.json", "universal-policy-package.json")
    }
    original = values[resource_name]
    assert original is not None
    if failure == "missing":
        values[resource_name] = None
    elif failure == "malformed":
        values[resource_name] = b"{"
    elif failure == "oversized":
        values[resource_name] = b" " * 4096 + original
    elif failure == "nested":
        values[resource_name] = b"[" * 1500 + b"0" + b"]" * 1500
    else:
        changed = json.loads(original)
        if failure == "digest":
            changed["artifact_sha256"] = "0" * 64
        else:
            changed["exports"][0]["contract_id"] = "untrusted.contract"
        values[resource_name] = json.dumps(changed).encode()
    monkeypatch.setattr(policy, "files", lambda _: Package(values))
    proposed = descriptor()
    with pytest.raises(SetupError, match="Selected policy"):
        policy.require_policy_package(proposed)
    assert proposed.database_packages == []


def test_equivalent_resource_formatting_preserves_exact_pins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = files("seller_agent_setup")
    values: dict[str, bytes | None] = {
        name: json.dumps(
            json.loads(root.joinpath(name).read_bytes()), indent=4
        ).encode()
        for name in ("runtime-policy-package.json", "universal-policy-package.json")
    }
    monkeypatch.setattr(policy, "files", lambda _: Package(values))
    result = policy.require_policy_package(descriptor())
    assert [item.module_key for item in result.database_packages] == [
        "cogit.runtime-policy",
        "cogit.universal-policy",
    ]
    assert policy.require_policy_package(result) == result
