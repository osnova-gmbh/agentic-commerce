"""Build reproducible, installable AgentDb bundles for the commerce modules.

The Python reference modules remain the behavioral oracle. Native SQL lives next
to each module under agentdb/; this command hashes it and writes the manifests
consumed by AgentDb's module deployment API. No server or credentials are needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from agentdb_sql import native_sql

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
EXPORTS = {
    "cogit-finance-catalog": {
        "queries": ["company.read", "companies.list", "sellers.list", "catalog.read", "evaluators.list"],
        "commands": ["company.upsert", "evaluator.upsert", "catalog.publish"],
    },
    "cogit-finance-deals": {
        "queries": ["outbox.pending", "deal.read", "deal.list", "ledger.balances"],
        "commands": ["deal.commit", "outbox.mark_sent", "intent.update"],
    },
    "cogit-messaging": {
        "queries": ["identity.resolve", "conversation.read"],
        "commands": ["identity.register", "type.register", "message.send", "message.claim", "message.ack", "message.release"],
    },
}
PREFIXES = {"cogit-finance-catalog": "ac_catalog", "cogit-finance-deals": "ac_deals", "cogit-messaging": "ac_msg"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build(root: Path = ROOT) -> dict:
    artifacts = {}
    for module, groups in EXPORTS.items():
        directory = root / "modules" / module / "agentdb"
        (directory / "migrations").mkdir(parents=True, exist_ok=True)
        (directory / "migrations" / "000001__native.sql").write_text(native_sql(module), encoding="utf-8", newline="\n")
        migrations = []
        for path in sorted((directory / "migrations").glob("*.sql")):
            migrations.append({"id": path.stem, "path": path.relative_to(directory).as_posix(), "sha256": digest(path.read_bytes())})
        if not migrations:
            raise ValueError(f"No native SQL migrations for {module}")
        exports = []
        prefix = PREFIXES[module]
        for kind, names in groups.items():
            for name in names:
                command = kind == "commands"
                exports.append({
                    "key": name, "kind": "command" if command else "query", "version": VERSION,
                    "contractId": f"{module}.{name}.v1", "functionName": f"{prefix}_{name.replace('.', '_')}",
                    "inputSchema": {"type": "object", "properties": {"payload": {"type": "string", "maxLength": 65536}}, "required": ["payload"], "additionalProperties": False},
                    "outputSchema": {"type": "object", "properties": {"result": {"type": "string", "maxLength": 65536}}, "required": ["result"], "additionalProperties": False},
                    "callerKinds": ["tenant_client", "fenced_worker"],
                    "capability": f"{prefix}.{'write' if command else 'read'}",
                    "policyScope": "tenant_module", "requiredPolicies": [],
                })
        wrappers = []
        for export in exports:
            capability = export["capability"]
            function = export["functionName"]
            operation = export["key"]
            wrappers.append(f"""CREATE FUNCTION {{{{tenantSchema}}}}.{function}(ctx jsonb, input jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  PERFORM core.require_module_context(ctx, '{module}', '{capability}', ARRAY['tenant_client','fenced_worker']);
  BEGIN
    RETURN jsonb_build_object('result', {{{{tenantSchema}}}}.{prefix}_dispatch(ctx, (input->>'payload')::jsonb, '{operation}')::text);
  EXCEPTION WHEN SQLSTATE 'P0200' THEN
    RETURN jsonb_build_object('result', jsonb_build_object('_module_error', SQLERRM)::text);
  END;
END $$;
ALTER FUNCTION {{{{tenantSchema}}}}.{function}(jsonb,jsonb) OWNER TO agentdb_owner;
REVOKE ALL ON FUNCTION {{{{tenantSchema}}}}.{function}(jsonb,jsonb) FROM PUBLIC;
""")
        wrapper_path = directory / "migrations" / "000099__exports.sql"
        wrapper_path.write_text("\n".join(wrappers), encoding="utf-8", newline="\n")
        migrations = [item for item in migrations if item["id"] != wrapper_path.stem]
        migrations.append({"id": wrapper_path.stem, "path": "migrations/" + wrapper_path.name, "sha256": digest(wrapper_path.read_bytes())})
        settings = {"type": "object", "properties": {"escrow_installation_id": {"type": "string", "maxLength": 128}, "operator_principal_id": {"type": "string", "maxLength": 128}}, "additionalProperties": False}
        defaults = {"escrow_installation_id": "cogit-finance", "operator_principal_id": ""}
        if module == "cogit-messaging":
            settings["properties"].update({"redeliver_after_s": {"type": "integer", "minimum": 1}, "max_delivery_attempts": {"type": "integer", "minimum": 1}})
            defaults.update(redeliver_after_s=30, max_delivery_attempts=5)
        manifest = {"formatVersion": 1, "moduleKey": module, "version": VERSION,
                    "platform": {"minSchema": 179, "maxSchema": 216}, "upgradeFrom": [],
                    "retention": "preserve", "migrations": migrations, "files": [],
                    "exports": exports, "resources": [], "settings": {"schema": settings, "defaults": defaults},
                    "policies": [], "evidence": []}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        artifacts[module] = {"directory": str(directory), "version": VERSION, "manifest_sha256": digest(canonical(manifest))}
    return artifacts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    print(json.dumps(build(parser.parse_args().root), indent=2))
