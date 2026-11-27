import json
from pathlib import Path

import pytest
from conftest import DIDS, ESCROW, NOTE_SCHEMA, Bench, code_of

CONTRACT_SCHEMAS = Path(__file__).resolve().parents[3] / "contracts" / "messages"


def test_migration_creates_the_three_prefixed_tables(bench):
    rows = bench.host.db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    assert [row["name"] for row in rows] == ["msg_agent_identities", "msg_message_types", "msg_messages"]


def test_identity_register_is_operator_only_and_upserts(bench):
    args = {"did": "did:key:zDave", "installation_id": "dave-agent", "org_id": "dave-co", "role": "seller"}
    assert code_of(bench.command, "dave-agent", "identity.register", args) == "forbidden"
    assert bench.command("operator", "identity.register", args, principal="operator") == {"did": "did:key:zDave"}
    bench.clock.advance(5)
    bench.command("operator", "identity.register", {**args, "org_id": "other-co"}, principal="operator")
    identity = bench.query("alice-agent", "identity.resolve", {"did": "did:key:zDave"})["identity"]
    assert identity == {
        "did": "did:key:zDave",
        "installation_id": "dave-agent",
        "org_id": "other-co",
        "role": "seller",
        "active": True,
        "registered_at": "2026-11-27T12:00:00Z",
    }
    assert code_of(bench.register, "x", "did:key:zX", role="banker") == "invalid_argument"


def test_identity_resolve_by_did_and_by_role(bench):
    bench.clock.advance(1)
    bench.register(ESCROW, "did:key:zEscrow", org_id="operator-co", role="escrow")
    bench.clock.advance(1)
    bench.register("escrow-2", "did:key:zEscrow2", org_id="other-co", role="escrow")
    resolve = lambda **args: bench.query("alice-agent", "identity.resolve", args)["identity"]  # noqa: E731
    assert resolve(did=DIDS["bob-agent"])["installation_id"] == "bob-agent"
    assert resolve(did="did:key:zNobody") is None
    assert resolve(role="escrow")["did"] == "did:key:zEscrow"  # the oldest match
    assert resolve(role="escrow", org_id="other-co")["did"] == "did:key:zEscrow2"
    assert resolve(role="evaluator") is None
    assert code_of(bench.query, "alice-agent", "identity.resolve", {}) == "invalid_argument"


def test_type_register_is_immutable_per_key_and_version(bench):
    register = lambda **args: bench.command(ESCROW, "type.register", args)  # noqa: E731
    same_bytes_other_order = dict(reversed(list(NOTE_SCHEMA.items())))
    assert register(type_key="test.note", type_version=1, json_schema=same_bytes_other_order) == {"status": "unchanged"}
    changed = {**NOTE_SCHEMA, "required": []}
    assert code_of(register, type_key="test.note", type_version=1, json_schema=changed) == "type_conflict"
    assert register(type_key="test.note", type_version=2, json_schema=changed) == {"status": "created"}
    row = bench.host.db.execute("SELECT * FROM msg_message_types WHERE type_version = 2").fetchone()
    assert row["registered_by"] == ESCROW and json.loads(row["json_schema"]) == changed


def test_type_register_is_for_the_escrow_installation_only(bench):
    args = {"type_key": "test.other", "type_version": 1, "json_schema": NOTE_SCHEMA}
    assert code_of(bench.command, "alice-agent", "type.register", args) == "forbidden"
    assert code_of(bench.command, "operator", "type.register", args, principal="operator") == "forbidden"
    other = Bench({"escrow_installation_id": "alice-agent"})
    assert other.command("alice-agent", "type.register", args) == {"status": "created"}


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "#/definitions/x"},
        {"type": "object", "properties": {"a": {"type": "string", "pattern": "^a"}}},
        {"type": "array", "items": {"oneOf": [{"type": "string"}]}},
        {"type": "object", "additionalProperties": True},
        {"type": "object", "additionalProperties": {"type": "string"}},
        {"type": ["string", "integer"]},
        {"type": "text"},
        {"type": "string", "format": "date-time"},
        {"type": "integer", "minimum": 0.5},
        {"type": "array", "items": [{"type": "string"}]},
        "not a schema",
    ],
)
def test_type_register_refuses_schemas_outside_the_dialect(bench, schema):
    args = {"type_key": "test.bad", "type_version": 1, "json_schema": schema}
    assert code_of(bench.command, ESCROW, "type.register", args) == "unsupported_schema"
    assert bench.host.db.execute("SELECT COUNT(*) FROM msg_message_types").fetchone()[0] == 1


def test_every_frozen_finance_schema_is_inside_the_dialect(bench):
    files = sorted(CONTRACT_SCHEMAS.glob("finance.*.v1.json"))
    if not files:
        pytest.skip("contracts/messages is not part of this checkout")
    for path in files:
        args = {
            "type_key": path.name.removesuffix(".v1.json"),
            "type_version": 1,
            "json_schema": json.loads(path.read_text()),
        }
        assert bench.command(ESCROW, "type.register", args) == {"status": "created"}, path.name
    assert len(files) >= 14
