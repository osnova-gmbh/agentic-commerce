"""Generate the explicit optional database descriptor from verified resources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, cast

import yaml
from cogit_agent_sdk import AgentServices
from cogit_agent_sdk.types import AgentDescriptor

ROOT = Path(__file__).resolve().parents[1]
if not (__name__ == "__main__" and "--installed" in sys.argv):
    sys.path.insert(0, str(ROOT / "src"))

from buyer_agent.database_bundle import (  # noqa: E402
    load_database_bundle,
)
from buyer_agent.database_example import (  # noqa: E402
    DatabaseAgent,
)


def database_manifest(base: Path) -> dict[str, Any]:
    """Keep the ordinary manifest untouched and select a queue-only pipeline."""
    try:
        payload = cast(dict[str, Any], yaml.safe_load(base.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("Could not read the base agent manifest") from exc
    bundle, digest = load_database_bundle()
    payload.setdefault("metadata", {})["entrypoint"] = (
        "buyer_agent.database_example:DatabaseAgent"
    )
    payload["database_packages"] = [
        {
            "module_key": bundle["moduleKey"],
            "version": bundle["version"],
            "artifact_sha256": digest,
            "exports": [
                {
                    "kind": export["kind"],
                    "key": export["key"],
                    "export_version": export["version"],
                    "contract_id": export["contractId"],
                }
                for export in bundle["exports"]
                if export["key"] in ("requests.put", "requests.get")
            ],
        }
    ]
    agent = DatabaseAgent()
    agent.configure(AgentServices())
    payload["actions"] = [
        binding.descriptor.model_dump(mode="json", by_alias=False)
        for binding in agent.action_bindings()
        if binding.descriptor.name == "persist_reference_request"
    ]
    payload["tools"] = []
    payload.pop("model", None)
    payload["pipelines"] = [
        {
            "name": "persist-reference-request",
            "description": "Persist then read typed data without a model call.",
            "applies_to": ["queue"],
            "steps": [
                {
                    "id": "persist",
                    "kind": "deterministic",
                    "invoke": "persist_reference_request",
                },
                {"id": "finish", "kind": "terminal"},
            ],
        }
    ]
    # The durable worker owns one fenced claim per process.
    payload.setdefault("runtime", {}).setdefault("worker", {})["concurrency"] = 1
    payload["runtime"]["model"] = {"profile": "disabled"}
    descriptor_fields = set(AgentDescriptor.model_fields)
    AgentDescriptor.model_validate(
        {k: v for k, v in payload.items() if k in descriptor_fields}
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "cogit.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "cogit.database.yaml")
    parser.add_argument(
        "--installed",
        action="store_true",
        help="Import the noneditable installed agent instead of checkout source",
    )
    args = parser.parse_args()
    try:
        manifest = database_manifest(args.base)
        args.output.write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Database example configuration failed: {exc}\n")
    print(
        f"Generated {args.output}; "
        "install its declared package before starting the worker."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
