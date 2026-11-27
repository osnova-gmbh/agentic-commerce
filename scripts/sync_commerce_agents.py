"""Synchronize executable action contracts and pin native module requirements."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from build_agentdb_modules import build, canonical, digest
from run_demo import configure_paths

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "cogit_finance": ROOT / "packages/cogit-finance",
    **{
        name.replace("-", "_"): ROOT / "agents" / name
        for name in ("buyer-agent", "seller-agent", "evaluator-agent")
    },
}


def synchronize() -> None:
    configure_paths()
    from cogit_agent_sdk.operations import export_action_contract

    build()
    for package, directory in PROJECTS.items():
        setup = importlib.import_module(package + "_setup")
        path = directory / "cogit.yaml"
        manifest = setup.read_manifest(path)
        agent = setup.configured_agent(manifest)
        manifest["actions"] = [
            b.descriptor.model_dump(mode="json", by_alias=False)
            for b in agent.action_bindings()
        ]
        native = []
        modules = ["cogit-messaging"]
        if package != "evaluator_agent":
            modules.append("cogit-finance-catalog")
        if package == "cogit_finance":
            modules.append("cogit-finance-deals")
        for module in modules:
            bundle = json.loads(
                (ROOT / "modules" / module / "agentdb/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            exports = bundle["exports"]
            if package != "cogit_finance":
                exports = [
                    e
                    for e in exports
                    if e["key"]
                    not in (
                        "identity.register",
                        "type.register",
                        "company.upsert",
                        "evaluator.upsert",
                    )
                ]
            if package == "buyer_agent":
                exports = [e for e in exports if e["key"] != "catalog.publish"]
            native.append(
                {
                    "module_key": module,
                    "version": bundle["version"],
                    "artifact_sha256": digest(canonical(bundle)),
                    "exports": [
                        {
                            "kind": e["kind"],
                            "key": e["key"],
                            "export_version": e["version"],
                            "contract_id": e["contractId"],
                        }
                        for e in exports
                    ],
                }
            )
        old = [
            entry
            for entry in manifest.get("database_packages", [])
            if entry["module_key"]
            not in ("cogit-messaging", "cogit-finance-catalog", "cogit-finance-deals")
        ]
        manifest["database_packages"] = old + native
        setup.write_manifest(path, manifest)
        (directory / "action-contract.v1.json").write_text(
            json.dumps(export_action_contract(agent.action_bindings()), indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(
            f"Synced {package}: {len(manifest['actions'])} actions, {len(native)} native modules"
        )


if __name__ == "__main__":
    synchronize()
