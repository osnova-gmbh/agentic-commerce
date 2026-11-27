"""Ports the demo code depends on. Hosts (AgentDb, the Cogit runtime, a bank) implement them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModuleError(Exception):
    """A module export refused the call. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


class BankError(Exception):
    """The bank refused a call. ``code`` mirrors the ``error`` field of its answer."""

    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(f"{status} {code}: {message}" if message else f"{status} {code}")
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Caller:
    """Who calls a module export. AgentDb supplies this from its own module context."""

    installation_id: str
    principal: str = "installation"  # installation | operator | operator_ro


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str  # succeeded | failed
    output: dict | None = None
    error: str | None = None


class ModulePort(Protocol):
    """Mirror of the SDK's DatabaseSeams: read with a query, change with a command."""

    def module_query(self, module: str, export: str, args: dict | None = None) -> dict: ...

    def module_command(self, module: str, export: str, args: dict | None = None, *, idempotency_key: str) -> dict:
        """The key names the business operation; a repeat returns the first result."""
        ...


class ArtifactPort(Protocol):
    def put(self, data: bytes, media_type: str) -> dict:
        """Store bytes; return ``{artifact_id, sha256, byte_length, media_type}``."""
        ...

    def get(self, artifact_id: str) -> bytes: ...

    def stat(self, artifact_id: str) -> dict | None: ...


class WorkPort(Protocol):
    """Admit one action of one installation as work. The same key yields the same run."""

    def admit(self, installation_id: str, action: str, input: dict, *, idempotency_key: str) -> str: ...

    def result(self, run_id: str) -> RunResult: ...


class BankPort(Protocol):
    def transfer(
        self,
        *,
        from_iban: str,
        to_iban: str,
        amount_minor: int,
        currency: str,
        reference: str,
        idempotency_key: str,
    ) -> dict: ...

    def lookup(self, idempotency_key: str) -> dict | None: ...

    def credits(self, iban: str, after: str = "0") -> list[dict]: ...

    def accounts(self) -> list[dict]: ...
