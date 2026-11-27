import pytest

from cogit_finance_seams import (
    Caller,
    LocalArtifacts,
    LocalModuleHost,
    LocalRuntime,
    ModuleError,
    SqliteModule,
)


class Notes(SqliteModule):
    name = "notes"
    migrations = ("CREATE TABLE notes (id TEXT PRIMARY KEY, text TEXT NOT NULL, owner TEXT NOT NULL);",)
    queries = {"note.list": "list_notes"}
    commands = {"note.add": "add", "note.add_then_fail": "add_then_fail"}

    def list_notes(self, args: dict, caller: Caller) -> dict:
        rows = self.db.execute("SELECT id, text, owner FROM notes ORDER BY id").fetchall()
        return {"notes": [dict(row) for row in rows]}

    def add(self, args: dict, caller: Caller) -> dict:
        self.db.execute("INSERT INTO notes VALUES (?, ?, ?)", (args["id"], args["text"], caller.installation_id))
        return {"id": args["id"]}

    def add_then_fail(self, args: dict, caller: Caller) -> dict:
        self.add(args, caller)
        raise ModuleError("boom")


@pytest.fixture()
def host() -> LocalModuleHost:
    host = LocalModuleHost()
    host.install(Notes())
    return host


def test_command_then_query_sees_the_caller(host):
    port = host.port("alice")
    assert port.module_command("notes", "note.add", {"id": "1", "text": "hi"}, idempotency_key="a") == {"id": "1"}
    assert port.module_query("notes", "note.list") == {"notes": [{"id": "1", "text": "hi", "owner": "alice"}]}


def test_failed_command_rolls_back(host):
    port = host.port("alice")
    with pytest.raises(ModuleError) as error:
        port.module_command("notes", "note.add_then_fail", {"id": "1", "text": "hi"}, idempotency_key="a")
    assert error.value.code == "boom"
    assert port.module_query("notes", "note.list") == {"notes": []}


def test_command_replay_returns_the_first_result(host):
    port = host.port("alice")
    first = port.module_command("notes", "note.add", {"id": "1", "text": "hi"}, idempotency_key="k1")
    again = port.module_command("notes", "note.add", {"id": "1", "text": "hi"}, idempotency_key="k1")
    assert first == again == {"id": "1"}
    assert len(port.module_query("notes", "note.list")["notes"]) == 1


def test_read_only_identity_cannot_run_commands(host):
    reader = host.port("dashboard", "operator_ro")
    assert reader.module_query("notes", "note.list") == {"notes": []}
    with pytest.raises(ModuleError) as error:
        reader.module_command("notes", "note.add", {"id": "1", "text": "hi"}, idempotency_key="a")
    assert error.value.code == "read_only"


def test_unknown_export_and_wrong_kind(host):
    port = host.port("alice")
    with pytest.raises(ModuleError) as error:
        port.module_query("notes", "note.add", {})
    assert error.value.code == "unknown_export"
    with pytest.raises(ModuleError) as error:
        port.module_query("nope", "x")
    assert error.value.code == "unknown_module"


def test_artifacts_are_content_addressed():
    store = LocalArtifacts()
    ref = store.put(b"hello", "text/plain")
    assert ref["byte_length"] == 5 and len(ref["sha256"]) == 64
    assert store.put(b"hello", "text/plain") == ref
    assert store.get(ref["artifact_id"]) == b"hello"
    assert store.stat(ref["artifact_id"]) == ref
    assert store.stat("missing") is None
    with pytest.raises(ModuleError):
        store.get("missing")


class Counter:
    def __init__(self) -> None:
        self.calls = 0
        self.fail_first = False

    def bump(self, by: int) -> dict:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("first attempt fails")
        return {"calls": self.calls, "by": by}


def test_runtime_runs_once_per_key():
    runtime, agent = LocalRuntime(), Counter()
    runtime.register("a", agent)
    run = runtime.admit("a", "bump", {"by": 2}, idempotency_key="k")
    assert runtime.admit("a", "bump", {"by": 2}, idempotency_key="k") == run
    assert agent.calls == 1
    assert runtime.result(run).status == "succeeded"
    assert runtime.result(run).output == {"calls": 1, "by": 2}


def test_runtime_retries_a_failed_run_under_the_same_id():
    runtime, agent = LocalRuntime(), Counter()
    agent.fail_first = True
    runtime.register("a", agent)
    run = runtime.admit("a", "bump", {"by": 1}, idempotency_key="k")
    assert runtime.result(run).status == "failed"
    assert runtime.admit("a", "bump", {"by": 1}, idempotency_key="k") == run
    assert runtime.result(run).status == "succeeded"
    assert agent.calls == 2


def test_runtime_accepts_an_invoker_callable():
    runtime, seen = LocalRuntime(), []

    def invoker(action: str, payload: dict, key: str) -> dict:
        seen.append((action, payload, key))
        return {"ok": True}

    runtime.register("a", invoker)
    run = runtime.admit("a", "tick", {}, idempotency_key="t1")
    assert runtime.result(run).output == {"ok": True}
    assert seen == [("tick", {}, "t1")]
