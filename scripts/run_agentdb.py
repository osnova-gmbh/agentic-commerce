"""Build, deploy and run commerce on a local AgentDb with four Cogit workers.

python scripts/run_agentdb.py prepare
python scripts/run_agentdb.py up --agentdb-root C:/cogit/cogit-core/agent-db
python scripts/run_agentdb.py serve
python scripts/run_agentdb.py status
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from run_demo import configure_paths, ensure_bank

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state/agentdb"


def env_file():
    values = {}
    for line in (STATE / ".env").read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def bind_receipts(routes):
    path = ROOT / "agents/buyer-agent/scripts/worker_cohort.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("receipt_helper", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    for route in routes.values():
        cohort = Path(route["cohort"])
        receipt = cohort / "receipt.json"
        ids = {
            key: route[key]
            for key in (
                "tenantId",
                "installationId",
                "definitionId",
                "versionId",
                "deploymentId",
                "poolId",
                "agentPrincipalId",
            )
        }
        published = {key: route[key] for key in ("executableSha256", "manifestSha256")}
        if receipt.exists():
            old = json.loads(receipt.read_text(encoding="utf-8"))
            if old["tenantId"] != ids["tenantId"] or any(
                old["route"].get(k) != v
                for k, v in {**ids, **published}.items()
                if k != "tenantId"
            ):
                raise ValueError(
                    "An existing cohort receipt belongs to a different deployment"
                )
        else:
            helper.receipt(cohort, ids, published)


def run_until_complete(client, role, command, routes, key, *, timeout=120):
    run_id = client.admit(routes[role]["installationId"], command, {}, key)
    deadline = time.monotonic() + timeout
    pause = threading.Event()
    while time.monotonic() < deadline:
        state = client.run(run_id)["lifecycle"]
        if state in {"completed", "succeeded"}:
            return run_id
        if state in {"failed", "cancelled"}:
            raise RuntimeError(f"{role}.{command} failed; inspect AgentDb run {run_id}")
        pause.wait(0.5)
    raise TimeoutError(
        f"Timed out waiting for {role}.{command}; run {run_id} remains recorded"
    )


def serve(port, bank_url):
    configure_paths()
    import uvicorn
    from cogit_messaging_shim import AgentKey
    from dashboard.agentdb import AgentDbClient, AgentDbEngine, create_agentdb_app

    saved = json.loads((STATE / "routes.json").read_text(encoding="utf-8"))
    routes = saved["routes"]
    bind_receipts(routes)
    secrets = env_file()
    roles = {
        "buyer-agent": ("buyer-co", "buyer"),
        "seller-agent": ("seller-co", "seller"),
        "evaluator-agent": ("operator-co", "evaluator"),
        "cogit-finance": ("operator-co", "escrow"),
    }
    keys, identities = {}, {}
    for name, (org, role) in roles.items():
        keys[name] = STATE / "keys" / (name + ".key")
        key = AgentKey.load_or_create(keys[name])
        identities[name] = {
            "did": key.did,
            "installation_id": routes[name]["installationId"],
            "org_id": org,
            "role": role,
        }
    identity_file = STATE / "identities.json"
    identity_file.write_text(json.dumps(identities, indent=2) + "\n", encoding="utf-8")
    bank_server, bank_thread = ensure_bank(bank_url)
    processes, logs = [], []
    launch_specs = []
    shutdown = threading.Event()
    monitor = None
    client = AgentDbClient(
        saved["apiUrl"], secrets["LOCAL_COMMERCE_CLIENT_TOKEN"], saved["tenantId"]
    )
    engine = None
    try:
        cogit = shutil.which("cogit")
        if cogit is None:
            raise RuntimeError("The Cogit CLI is not installed")
        for name, route in routes.items():
            base = dict(os.environ)
            for key in list(base):
                if key.startswith("COGIT_AGENTDB_") or key == "DATABASE_URL":
                    del base[key]
            base.update(
                {
                    "COGIT_DEV_MODE": "0",
                    "COGIT_COMMERCE_NATIVE_MODULES": "1",
                    "COGIT_TENANT_ID": saved["tenantId"],
                    "COGIT_AGENTDB_URL": saved["apiUrl"],
                    "COGIT_AGENTDB_API_VERSION": "0.1.0",
                    "COGIT_AGENTDB_INSTALLATION_ID": route["installationId"],
                    "COGIT_AGENTDB_POOL_ID": route["poolId"],
                    "COGIT_AGENTDB_WORKER_TOKEN": secrets["AGENTDB_WORKER_CREDENTIAL"],
                    "COGIT_AGENTDB_LOOP_INTEGRITY_KEY": secrets[
                        "LOCAL_COMMERCE_LOOP_KEY"
                    ],
                    "COGIT_AGENTDB_COHORT_RECEIPT": str(
                        Path(route["cohort"]) / "receipt.json"
                    ),
                    "AGENT_KEY_FILE": str(keys[name]),
                    "ESCROW_DID": identities["cogit-finance"]["did"],
                    "SIM_BANK_URL": bank_url,
                    "COGIT_COMMERCE_DATA_DIR": str(ROOT / "data/demo"),
                    "COGIT_COMMERCE_IDENTITIES_FILE": str(identity_file),
                }
            )
            log_file = (STATE / (name + ".log")).open("ab")
            logs.append(log_file)
            process = subprocess.Popen(
                [cogit, "work", "--project", route["project"], "--environment"],
                cwd=route["project"],
                env=base,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            processes.append(process)
            launch_specs.append((base, route["project"], log_file))
            print(f"Started {name} worker (PID {process.pid})", flush=True)

        def supervise():
            while not shutdown.wait(3):
                for index, process in enumerate(processes):
                    if process.poll() is not None and not shutdown.is_set():
                        env, project, log_file = launch_specs[index]
                        print(
                            f"Restarting stopped worker for {Path(project).name}",
                            flush=True,
                        )
                        processes[index] = subprocess.Popen(
                            [cogit, "work", "--project", project, "--environment"],
                            cwd=project,
                            env=env,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if os.name == "nt"
                            else 0,
                        )

        monitor = threading.Thread(
            target=supervise, daemon=True, name="commerce-worker-supervisor"
        )
        monitor.start()
        seed_digest = hashlib.sha256(
            identity_file.read_bytes()
            + b"".join(
                p.read_bytes() for p in sorted((ROOT / "data/demo").glob("*.yaml"))
            )
        ).hexdigest()[:20]
        for role, command in [
            ("cogit-finance", "bootstrap"),
            ("cogit-finance", "tick"),
            ("seller-agent", "publish_catalog"),
        ]:
            run_until_complete(
                client, role, command, routes, f"setup:{seed_digest}:{role}:{command}"
            )
        engine = AgentDbEngine(client, routes, STATE, bank_url=bank_url)
        engine.start_scheduler()
        app = create_agentdb_app(engine)

        @app.get("/api/runtime")
        def runtime():
            workers = {
                name: {"pid": process.pid, "running": process.poll() is None}
                for name, process in zip(routes, processes)
            }
            return {
                "mode": "agentdb",
                "api_url": saved["apiUrl"],
                "workers": workers,
                "ready": all(w["running"] for w in workers.values()),
                "scheduler_error": engine.error,
            }

        print(
            f"AgentDb transaction workspace: http://127.0.0.1:{port}/demo", flush=True
        )
        uvicorn.run(app, host="127.0.0.1", port=port)
    finally:
        shutdown.set()
        if monitor:
            monitor.join(timeout=5)
        if engine:
            engine.close()
        else:
            client.close()
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for log_file in logs:
            log_file.close()
        if bank_server is not None:
            bank_server.should_exit = True
            bank_thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prepare", "up", "serve", "status", "restart-backend")
    )
    parser.add_argument(
        "--agentdb-root",
        default=os.environ.get("AGENTDB_ROOT", "C:/cogit/cogit-core/agent-db"),
    )
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--bank-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    if args.command in {"prepare", "up"}:
        from prepare_agentdb import prepare

        plan = prepare(install=args.command == "up")
        if args.command == "prepare":
            return
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/agentdb_stack.mjs"),
                "start",
                "--agentdb-root",
                args.agentdb_root,
            ],
            check=True,
        )
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/agentdb_stack.mjs"),
                "deploy",
                "--plan",
                str(plan),
            ],
            check=True,
        )
    if args.command in {"up", "serve"}:
        serve(args.port, args.bank_url)
    elif args.command in {"status", "restart-backend"}:
        command = "restart" if args.command == "restart-backend" else "status"
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/agentdb_stack.mjs"),
                command,
                "--agentdb-root",
                args.agentdb_root,
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
