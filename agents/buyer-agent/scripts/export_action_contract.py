"""Export the versioned action contract artifact from live bindings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manifest_sync import export_action_contract_file  # noqa: E402

from buyer_agent_setup.errors import (  # noqa: E402
    diagnostic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write action-contract.v1.json from configured agent bindings.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "action-contract.v1.json",
        help="Output path for the action contract artifact",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        export_action_contract_file(args.output)
        print(f"exported action contract to {args.output}")
        return 0
    except Exception as exc:
        print(f"Action contract export failed: {diagnostic(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
