"""Screenshot the dashboard on fixture sets with Playwright (Chromium).

    python3 apps/dashboard/scripts/screenshots.py --server-python .venv/bin/python

Starts ``python -m dashboard --fixtures <set>`` for every set under ``fixtures/`` (or the
ones given as ``name=directory``) and writes ``docs/<name>.png``. Playwright only has to be
importable by the interpreter that runs this script; the dashboard runs under
``--server-python``.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_up(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    while True:
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except OSError:
            if process.poll() is not None or time.monotonic() > deadline:
                raise SystemExit(f"the dashboard did not start on {url}") from None
            time.sleep(0.1)


def shoot(browser, name: str, directory: str, args: argparse.Namespace) -> None:
    port = free_port()
    command = [args.server_python, "-m", "dashboard", "--fixtures", directory, "--port", str(port)]
    server = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_until_up(f"http://127.0.0.1:{port}/health", server)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        problems: list[str] = []
        page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.on("requestfailed", lambda request: problems.append(f"failed: {request.url}"))
        page.goto(f"http://127.0.0.1:{port}/")
        page.wait_for_selector(".steps")
        page.wait_for_timeout(1300)  # one more poll, so the picture is of a settled page
        target = args.out / f"{name}.png"
        page.screenshot(path=str(target), full_page=True)
        loaded = page.evaluate("performance.getEntriesByType('resource').map(entry => entry.name)")
        foreign = [url for url in loaded if not url.startswith(f"http://127.0.0.1:{port}/")]
        print(f"{target}  problems={problems}  foreign_hosts={foreign}")
        page.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sets", nargs="*", help="name=directory; default: every set under fixtures/")
    parser.add_argument("--server-python", default=sys.executable, help="interpreter that has the dashboard installed")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    sets = dict(item.split("=", 1) for item in args.sets) or {
        path.name: str(path) for path in sorted((ROOT / "fixtures").iterdir()) if (path / "deals.json").is_file()
    }
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, directory in sets.items():
            shoot(browser, name, directory, args)
        browser.close()


if __name__ == "__main__":
    main()
