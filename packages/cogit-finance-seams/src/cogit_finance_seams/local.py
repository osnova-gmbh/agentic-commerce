"""In-process stand-ins for AgentDb: module host, artifact store and work admission.

They exist so the whole deal flow runs and is tested without Docker. They are not a
second implementation of AgentDb; the real adapters replace them on a deployment.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .protocols import Caller, ModuleError, RunResult


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dumps(value: Any) -> str:
    """JSON text for a TEXT column."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def loads(text: str | None) -> Any:
    return None if text is None else json.loads(text)


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, allow_nan=False))


class SqliteModule:
    """Base for a module's reference implementation.

    Subclasses set ``name``, ``migrations_dir`` (or ``migrations``), and map export
    names to method names in ``queries`` and ``commands``. Handlers have the signature
    ``handler(self, args: dict, caller: Caller) -> dict``. A command runs inside one
    transaction; raising rolls it back.
    """

    name: str = ""
    migrations: tuple[str, ...] = ()
    migrations_dir: Path | None = None
    queries: dict[str, str] = {}
    commands: dict[str, str] = {}

    host: "LocalModuleHost"
    db: sqlite3.Connection
    settings: dict

    def attach(self, host: "LocalModuleHost", settings: dict | None = None) -> None:
        self.host = host
        self.db = host.db
        self.settings = dict(settings or {})
        for script in self.load_migrations():
            self.db.executescript(script)

    def load_migrations(self) -> list[str]:
        scripts = list(self.migrations)
        if self.migrations_dir is not None:
            scripts += [path.read_text(encoding="utf-8") for path in sorted(Path(self.migrations_dir).glob("*.sql"))]
        return scripts

    def now(self) -> datetime:
        return self.host.clock()

    def now_ts(self) -> str:
        return to_ts(self.now())

    @staticmethod
    def require_operator(caller: Caller) -> None:
        if caller.principal != "operator":
            raise ModuleError("forbidden", "operator only")


class LocalModuleHost:
    """Runs module reference implementations over one in-memory SQLite database."""

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self.clock = clock
        self.db = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._modules: dict[str, SqliteModule] = {}
        self._replays: dict[tuple, Any] = {}

    def install(self, module: SqliteModule, settings: dict | None = None) -> None:
        with self._lock:
            if module.name in self._modules:
                raise ModuleError("already_installed", module.name)
            module.attach(self, settings)
            self._modules[module.name] = module

    def port(self, installation_id: str, principal: str = "installation") -> "LocalModulePort":
        return LocalModulePort(self, Caller(installation_id, principal))

    def call(
        self, caller: Caller, kind: str, module: str, export: str, args: dict | None, idempotency_key: str | None = None
    ) -> dict:
        if kind == "command" and not idempotency_key:
            raise ModuleError("idempotency_key_required", f"{module}.{export}")
        with self._lock:
            target = self._modules.get(module)
            if target is None:
                raise ModuleError("unknown_module", module)
            method = (target.queries if kind == "query" else target.commands).get(export)
            if method is None:
                raise ModuleError("unknown_export", f"{module}.{export} is not a {kind}")
            payload = _json_copy(args or {})
            if kind == "query":
                return _json_copy(getattr(target, method)(payload, caller) or {})
            if caller.principal == "operator_ro":
                raise ModuleError("read_only", "this identity may only run queries")
            replay_key = (caller.installation_id, module, export, idempotency_key)
            if replay_key in self._replays:
                return _json_copy(self._replays[replay_key])
            self.db.execute("BEGIN IMMEDIATE")
            try:
                result = _json_copy(getattr(target, method)(payload, caller) or {})
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self._replays[replay_key] = result
            return _json_copy(result)


class LocalModulePort:
    def __init__(self, host: LocalModuleHost, caller: Caller) -> None:
        self._host = host
        self.caller = caller

    def module_query(self, module: str, export: str, args: dict | None = None) -> dict:
        return self._host.call(self.caller, "query", module, export, args)

    def module_command(self, module: str, export: str, args: dict | None = None, *, idempotency_key: str) -> dict:
        return self._host.call(self.caller, "command", module, export, args, idempotency_key)


class LocalArtifacts:
    """Content-addressed artifact store. Readable tenant-wide, like AgentDb in one tenant."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, tuple[bytes, dict]] = {}

    def put(self, data: bytes, media_type: str) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        ref = {
            "artifact_id": f"art_{digest[:24]}",
            "sha256": digest,
            "byte_length": len(data),
            "media_type": media_type,
        }
        with self._lock:
            self._items[ref["artifact_id"]] = (bytes(data), ref)
        return dict(ref)

    def get(self, artifact_id: str) -> bytes:
        with self._lock:
            item = self._items.get(artifact_id)
        if item is None:
            raise ModuleError("artifact_not_found", artifact_id)
        return item[0]

    def stat(self, artifact_id: str) -> dict | None:
        with self._lock:
            item = self._items.get(artifact_id)
        return None if item is None else dict(item[1])


@dataclass
class RunRecord:
    run_id: str
    installation_id: str
    action: str
    input: dict
    idempotency_key: str
    status: str = "failed"
    output: dict | None = None
    error: str | None = None
    trace: str | None = None
    attempts: int = 0


@dataclass
class LocalRuntime:
    """Admits work to registered agent objects and runs it synchronously.

    The same idempotency key returns the same run. A succeeded run is never executed
    again; a failed run is executed again on re-admission, like a retried job.
    """

    agents: dict[str, Any] = field(default_factory=dict)
    runs: dict[str, RunRecord] = field(default_factory=dict)
    _by_key: dict[tuple[str, str], str] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def register(self, installation_id: str, agent: Any) -> None:
        """Register a plain object (actions are its methods) or an invoker
        ``callable(action, input, idempotency_key) -> dict``."""
        self.agents[installation_id] = agent

    def admit(self, installation_id: str, action: str, input: dict, *, idempotency_key: str) -> str:
        with self._lock:
            agent = self.agents.get(installation_id)
            if agent is None:
                raise ModuleError("unknown_installation", installation_id)
            key = (installation_id, idempotency_key)
            run_id = self._by_key.get(key)
            if run_id is None:
                run_id = f"run_{len(self.runs) + 1:05d}"
                self._by_key[key] = run_id
                self.runs[run_id] = RunRecord(run_id, installation_id, action, _json_copy(input), idempotency_key)
            record = self.runs[run_id]
            if record.status == "succeeded":
                return run_id
            record.attempts += 1
            try:
                if callable(agent):
                    output = agent(action, _json_copy(input), idempotency_key)
                else:
                    output = getattr(agent, action)(**_json_copy(input))
                record.output = _json_copy(output) if output is not None else {}
                record.status, record.error, record.trace = "succeeded", None, None
            except Exception as exc:  # the run failed; the caller decides whether to retry
                record.status = "failed"
                record.error = f"{type(exc).__name__}: {exc}"
                record.trace = traceback.format_exc()
            return run_id

    def result(self, run_id: str) -> RunResult:
        record = self.runs[run_id]
        return RunResult(record.run_id, record.status, record.output, record.error)
