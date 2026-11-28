"""Execute the generated SQL on PostgreSQL, separate from AgentDb API acceptance.

Set COMMERCE_SQL_TEST_DSN to a disposable PostgreSQL database. Each test uses a
random schema, never modifies core, and drops only that schema during teardown.
The domain dispatcher is invoked directly here; full worker/context checks are
performed by scripts/verify_agentdb.py against the real AgentDb deployment.
"""

import copy
import json
import os
import re
import uuid

import pytest

from cogit_finance_seams import Caller, ModuleError
from world import BUYER, ESCROW, REPO, SELLER, DemoWorld

DSN = os.environ.get("COMMERCE_SQL_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="COMMERCE_SQL_TEST_DSN is required for native PostgreSQL execution"
)
PREFIXES = {
    "cogit-messaging": "ac_msg",
    "cogit-finance-catalog": "ac_catalog",
    "cogit-finance-deals": "ac_deals",
}


class NativeHost:
    def __init__(self, connection, schema):
        self.db, self.schema = connection, schema
        self.modules, self.settings, self.replays = {}, {}, {}

    def install(self, module, settings=None):
        self.modules[module.name] = module
        self.settings[module.name] = {
            "escrow_installation_id": ESCROW,
            "operator_principal_id": "test-operator",
            "operator_readonly_principal_id": "test-reader",
            "redeliver_after_s": 30,
            "max_delivery_attempts": 5,
            **(settings or {}),
        }

    def port(self, installation_id, principal="installation"):
        host = self
        caller = Caller(installation_id, principal)

        class Port:
            def module_query(self, module, export, args=None):
                return host.call(caller, "query", module, export, args)

            def module_command(self, module, export, args=None, *, idempotency_key):
                return host.call(
                    caller, "command", module, export, args, idempotency_key
                )

        return Port()

    def call(self, caller, kind, module, export, args=None, key=None):
        target = self.modules[module]
        exports = target.queries if kind == "query" else target.commands
        if export not in exports:
            raise ModuleError("unknown_export")
        if kind == "command" and caller.principal == "operator_ro":
            raise ModuleError("read_only")
        replay = (caller.installation_id, module, export, key)
        if kind == "command" and replay in self.replays:
            return copy.deepcopy(self.replays[replay])
        ctx = {
            "tenantId": "00000000-0000-4000-8000-000000000001",
            "installationId": caller.installation_id,
            "principalId": "test-operator"
            if caller.principal == "operator"
            else "test-reader",
            "callerKind": "tenant_client"
            if caller.principal != "installation"
            else "fenced_worker",
            "settings": self.settings[module],
        }
        import psycopg2
        from psycopg2 import sql

        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT {}.{}(%s::jsonb,%s::jsonb,%s)").format(
                        sql.Identifier(self.schema),
                        sql.Identifier(PREFIXES[module] + "_dispatch"),
                    ),
                    (json.dumps(ctx), json.dumps(args or {}), export),
                )
                result = cursor.fetchone()[0]
        except psycopg2.Error as exc:
            if exc.pgcode == "P0200":
                raise ModuleError(exc.diag.message_primary) from exc
            raise
        if kind == "command":
            self.replays[replay] = copy.deepcopy(result)
        return result


@pytest.fixture
def native_host():
    import psycopg2
    from psycopg2 import sql

    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    schema = "commerce_test_" + uuid.uuid4().hex
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        for module in PREFIXES:
            directory = REPO / "modules" / module / "agentdb/migrations"
            source = "\n".join((directory / name).read_text(encoding="utf-8") for name in (
                "000001__native.sql", "000100__spec_recovery.sql"))
            source = re.sub(
                r"(?:ALTER (?:TABLE|FUNCTION).*?OWNER TO agentdb_owner;|REVOKE ALL .*? FROM PUBLIC;)",
                "",
                source,
                flags=re.S,
            )
            cursor.execute(source.replace("{{tenantSchema}}", '"' + schema + '"'))
    try:
        yield NativeHost(connection, schema)
    finally:
        assert re.fullmatch(r"commerce_test_[0-9a-f]{32}", schema)
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
        connection.close()


@pytest.mark.parametrize("seller_mode", ["ok", "broken"])
def test_native_sql_drives_actual_agent_actions(
    native_host, monkeypatch, tmp_path, seller_mode
):
    import cogit_messaging_shim.testing as transport

    monkeypatch.setattr(transport, "LocalModuleHost", lambda *args: native_host)
    world = DemoWorld(tmp_path, seller_mode)
    try:
        world.tick()
        world.act(SELLER, "publish_catalog")
        deal_id = world.act(BUYER, "start_purchase")["deal_id"]
        assert world.run(deal_id) == "SETTLED"
        from world import chain_is_valid
        events = world.deal(deal_id)["events"]
        assert chain_is_valid(events)
        if seller_mode == "ok":
            assert [e["event_type"] for e in events] == [
                "service_request", "quote", "terms_proposed", "accept_terms", "accept_terms",
                "terms_countersigned", "payment_request", "funding_received", "delivery",
                "evaluation_requested", "verdict", "verdict", "verdict", "decision",
                "payout_submitted", "payout_confirmed", "receipt",
            ]
        else:
            assert len(world.deal(deal_id)["deliveries"]) == 2
            assert any(row.get("reason") == "stale_verdict" for row in world.conversation(deal_id))
        assert world.balances(deal_id) == {
            "held": 0,
            "seller": 49500,
            "fee": 500,
            "buyer_refund": 0,
            "returned": 0,
        }
        with pytest.raises(ModuleError, match="forbidden"):
            native_host.port(BUYER).module_command(
                "cogit-finance-deals",
                "outbox.mark_sent",
                {"outbox_id": "anything"},
                idempotency_key="forbidden-write",
            )
    finally:
        world.close()


@pytest.mark.parametrize("module,export,payload", [
    ("cogit-finance-catalog", "company.upsert", {
        "company": {"org_id": "test-seller", "legal_name": "Test Seller", "roles": ["seller"]},
    }),
    ("cogit-messaging", "identity.register", {
        "did": "did:key:test-buyer", "installation_id": "buyer-agent", "org_id": "buyer-co", "role": "buyer",
    }),
])
def test_native_privileged_writes_reject_missing_escrow_configuration(native_host, module, export, payload):
    from cogit_finance_catalog_module import CatalogModule
    from cogit_messaging_module import MessagingModule

    native_host.install(CatalogModule() if module == "cogit-finance-catalog" else MessagingModule())
    native_host.settings[module].pop("escrow_installation_id")
    with pytest.raises(ModuleError, match="forbidden"):
        native_host.port(BUYER).module_command(module, export, payload, idempotency_key="unauthorized")
    # A correctly configured operator remains authorized even without an escrow installation.
    result = native_host.port("operator", "operator").module_command(module, export, payload, idempotency_key="authorized")
    assert result
