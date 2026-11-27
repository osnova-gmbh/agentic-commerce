"""Host-only private portal oracle for a separately isolated worker container."""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from capability_proof.portal import Portal, Scenario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-directory", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    args.private_directory.mkdir(parents=True, exist_ok=False)
    portal = Portal(Scenario.create(args.seed))
    portal.start()
    try:
        ready = {
            "origin": portal.url.replace("127.0.0.1", "host.docker.internal"),
            "loginUrl": portal.login_url.replace("127.0.0.1", "host.docker.internal"),
            "expected": portal.expected_hashes(),
            "records": [
                {"number": item.number, "period": item.period, "total": item.total}
                for item in portal.scenario.records
            ],
        }
        (args.private_directory / "private-oracle.json").write_text(
            json.dumps(ready, indent=2), encoding="utf-8"
        )
        print(
            "Private portal ready; credentials and originals remain outside worker",
            flush=True,
        )
        pause = threading.Event()
        while not (args.private_directory / "stop").exists():
            with portal._mutex:  # fixture control plane, never exposed to the agent
                events = list(portal.events)
            (args.private_directory / "events.json").write_text(
                json.dumps(events, indent=2), encoding="utf-8"
            )
            pause.wait(1)
    finally:
        portal.close()


if __name__ == "__main__":
    main()
