"""``python -m dashboard --fixtures <dir>``: serve a fixture set on DASHBOARD_PORT (8090).

Live data needs ports only a host can supply, so it is wired in code:
``create_app(ModuleSource(modules, bank))``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from .app import create_app
from .sources import FixtureSource


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m dashboard", description="Read-only dashboard of escrow deals.")
    parser.add_argument("--fixtures", type=Path, required=True, help="directory with a fixture set (deals.json, ...)")
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8090")))
    args = parser.parse_args(argv)
    try:
        source = FixtureSource(args.fixtures)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    uvicorn.run(create_app(source), host=args.host, port=args.port, log_level=os.environ.get("DASHBOARD_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
