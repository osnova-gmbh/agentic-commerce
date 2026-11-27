"""Expose the existing commerce API over MCP (stdio or loopback HTTP)."""
from __future__ import annotations

import argparse
import os

from run_demo import configure_paths


def main() -> None:
    configure_paths()
    from dashboard.mcp_server import create_mcp_server

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("COMMERCE_API_URL", "http://127.0.0.1:8091"))
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--port", type=int, default=8094, help="Loopback HTTP port; ignored for stdio")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    server = create_mcp_server(args.api_url, port=args.port, transport=args.transport)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
