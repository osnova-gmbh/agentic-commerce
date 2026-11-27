"""``python -m sim_bank``: serve the bank on SIM_BANK_PORT (8080), seeded from SIM_BANK_SEED."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from .app import create_app


def main() -> None:
    seed = os.environ.get("SIM_BANK_SEED", "").strip()
    host = os.environ.get("SIM_BANK_HOST", "127.0.0.1")
    port = int(os.environ.get("SIM_BANK_PORT", "8080"))
    app = create_app(Path(seed) if seed else None)
    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("SIM_BANK_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
