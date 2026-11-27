"""Verify a real AgentDb-backed purchase and optionally restart the backend.

Run after run_agentdb.py up/serve is listening. This records evidence, checks all
four workers, verifies the signed event chain and balances, and reads the same
deal after a backend restart when --restart is requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import threading
import time
import uuid

from run_demo import configure_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8093")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    root = configure_paths()
    import httpx
    from cogit_messaging_shim import event_hash, verify_envelope

    with httpx.Client(base_url=args.url, timeout=25) as client:
        runtime = client.get("/api/runtime").raise_for_status().json()
        if (
            runtime["mode"] != "agentdb"
            or not runtime["ready"]
            or len(runtime["workers"]) != 4
        ):
            raise RuntimeError("Four live AgentDb workers are required")
        request = str(uuid.uuid4())
        admission = (
            client.post(
                "/api/demo/purchases",
                headers={"Idempotency-Key": request},
                json={"scenario": "happy"},
            )
            .raise_for_status()
            .json()
        )
        deadline = time.monotonic() + 180
        pause = threading.Event()
        while time.monotonic() < deadline:
            status = client.get("/api/demo/status").raise_for_status().json()
            if status.get("error"):
                raise RuntimeError(status["error"])
            if status.get("state") == "SETTLED":
                break
            pause.wait(1)
        else:
            raise TimeoutError("AgentDb purchase did not settle within 180 seconds")
        route = json.loads((root / ".state/agentdb/routes.json").read_text())
        from run_agentdb import env_file
        from dashboard.agentdb import AgentDbClient

        api = AgentDbClient(
            route["apiUrl"],
            env_file()["LOCAL_COMMERCE_CLIENT_TOKEN"],
            route["tenantId"],
        )
        try:
            raw = api.module_query(
                "cogit-finance-deals", "deal.read", {"deal_id": status["deal_id"]}
            )
            previous = "0" * 64
            for event in raw["events"]:
                assert event["prev_hash"] == previous and event["hash"] == event_hash(
                    event
                )
                previous = event["hash"]
                envelope = event["body"].get("envelope")
                if envelope:
                    assert verify_envelope(envelope)
            balances = api.module_query(
                "cogit-finance-deals", "ledger.balances", {"deal_id": status["deal_id"]}
            )
            assert balances == {
                "held": 0,
                "seller": 49500,
                "fee": 500,
                "buyer_refund": 0,
                "returned": 0,
            }
            delivery = (
                client.get(f"/api/demo/deals/{status['deal_id']}/delivery")
                .raise_for_status()
                .content
            )
            evidence = {
                "runtime": runtime,
                "admission": admission,
                "deal_id": status["deal_id"],
                "state": "SETTLED",
                "head_hash": previous,
                "balances": balances,
                "delivery_sha256": hashlib.sha256(delivery).hexdigest(),
                "restart_verified": False,
            }
            if args.restart:
                subprocess.run(
                    ["node", str(root / "scripts/agentdb_stack.mjs"), "restart"],
                    check=True,
                )
                recovered = api.module_query(
                    "cogit-finance-deals", "deal.read", {"deal_id": status["deal_id"]}
                )
                assert recovered == raw
                after = (
                    client.get(f"/api/demo/deals/{status['deal_id']}/delivery")
                    .raise_for_status()
                    .content
                )
                assert after == delivery
                evidence["restart_verified"] = True
        finally:
            api.close()
        destination = root / ".state/agentdb" / ("acceptance-" + request + ".json")
        destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(destination)


if __name__ == "__main__":
    main()
