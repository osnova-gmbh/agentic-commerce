"""Run the local transaction demo: python scripts/run_demo.py --port 8091."""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path


def configure_paths() -> Path:
    """Use this checkout and its pinned, pure-Python framework wheels."""
    root = Path(__file__).resolve().parents[1]
    paths = [root / "apps/dashboard/src", root / "apps/sim-bank/src"]
    paths += [
        project / "src"
        for group in ("agents", "packages", "modules")
        for project in (root / group).iterdir()
        if (project / "src").is_dir()
    ]
    wheels = root / "agents/buyer-agent/vendor/wheels"
    paths += [
        wheels / filename
        for filename in (
            "cogit_agent_sdk-0.5.16-py3-none-any.whl",
            "cogit_tool_core-0.1.3-py3-none-any.whl",
            "agentdb_client-0.2.13-py3-none-any.whl",
            "cogit_runtime-0.3.31-py3-none-any.whl",
        )
    ]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Missing demo dependency: {path}")
    sys.path[:0] = [str(path) for path in paths]
    return root


def ensure_bank(url: str):
    """Reuse an existing simulated bank, or start the default local bank."""
    import httpx
    import uvicorn

    from sim_bank import create_app

    def check() -> None:
        response = httpx.get(f"{url.rstrip('/')}/accounts", timeout=2)
        response.raise_for_status()
        if not isinstance(response.json().get("accounts"), list):
            raise RuntimeError(f"{url} is not a simulated bank")

    try:
        check()
        return None, None
    except httpx.ConnectError:
        if url.rstrip("/") != "http://127.0.0.1:8080":
            raise RuntimeError(f"Start the simulated bank at {url} first") from None

    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=8080))
    thread = threading.Thread(target=server.run, daemon=True, name="demo-bank")
    thread.start()
    pause = threading.Event()
    for _ in range(50):
        if server.started:
            check()
            return server, thread
        if not thread.is_alive():
            break
        pause.wait(0.1)
    server.should_exit = True
    raise RuntimeError("The simulated bank could not start on port 8080")


def main() -> None:
    root = configure_paths()
    import uvicorn

    from dashboard.checkout import CatalogDemoEngine, create_checkout_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--bank-url", default="http://127.0.0.1:8080")
    parser.add_argument("--step-delay", type=float, default=1.0)
    parser.add_argument("--history", type=Path, default=root / ".local/run-app/checkout-history.json")
    args = parser.parse_args()
    if not 0 <= args.step_delay <= 3:
        parser.error("--step-delay must be between 0 and 3 seconds")
    server, thread = ensure_bank(args.bank_url)
    engine = None
    try:
        engine = CatalogDemoEngine(root, bank_url=args.bank_url, step_delay=args.step_delay, history_file=args.history)
        print(f"Transaction demo: http://127.0.0.1:{args.port}/demo", flush=True)
        uvicorn.run(create_checkout_app(engine), host="127.0.0.1", port=args.port)
    finally:
        if engine is not None:
            engine.close()
        if server is not None:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
