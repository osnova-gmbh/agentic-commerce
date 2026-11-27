"""Validate cogit.yaml against its schema and executable binding contract."""

from __future__ import annotations

import sys
from pathlib import Path

from jsonschema.validators import validator_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cogit_runtime.manifest import generate_manifest_schema, load_manifest  # noqa: E402
from manifest_sync import (  # noqa: E402
    validate_action_contract_file,
    validate_manifest_file,
)

from evaluator_agent_setup import (  # noqa: E402
    configured_agent,
    read_manifest,
)
from evaluator_agent_setup.errors import (  # noqa: E402
    diagnostic,
)


def _validate() -> int:
    manifest_path = ROOT / "cogit.yaml"
    raw = read_manifest(manifest_path)
    schema = generate_manifest_schema()
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(raw)

    manifest = load_manifest(manifest_path)
    agent = configured_agent(raw)
    parity_errors = validate_manifest_file(manifest_path, agent)
    contract_path = ROOT / "action-contract.v1.json"
    parity_errors.extend(validate_action_contract_file(contract_path, agent))
    if parity_errors:
        for error in parity_errors:
            print(f"manifest parity error: {error}", file=sys.stderr)
        return 1

    print(
        "validated cogit.yaml and action contract: "
        f"{len(manifest.descriptor.actions)} actions, "
        f"{len(manifest.descriptor.tools or [])} tools, "
        f"{len(manifest.descriptor.pipelines or [])} pipelines"
    )
    return 0


def main() -> int:
    try:
        return _validate()
    except Exception as exc:
        print(f"Manifest validation failed: {diagnostic(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
