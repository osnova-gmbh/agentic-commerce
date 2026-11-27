"""Wait for an HTTP endpoint to return any response."""

from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(args.url, timeout=2):  # noqa: S310
                return 0
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {args.url}")


if __name__ == "__main__":
    raise SystemExit(main())
