"""One retained failed run must not poison recurring escrow processing."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from dashboard.agentdb import AgentDbClient, AgentDbEngine, PersistentScheduler, ROLES


class Runs:
    def __init__(self) -> None:
        self.admissions: dict[str, str] = {}
        self.states: dict[str, str] = {}

    def admit(self, installation_id: str, command: str, payload: dict, key: str) -> str:
        run = self.admissions.setdefault(key, str(uuid.uuid4()))
        self.states.setdefault(run, "running")
        return run

    def run(self, run_id: str) -> dict:
        return {"lifecycle": self.states[run_id]}


def test_failed_slot_is_archived_and_replaced_after_restart(tmp_path: Path) -> None:
    server = Runs()
    routes = {role: {"installationId": role} for role in ROLES}
    journal = tmp_path / "scheduler.json"
    first = PersistentScheduler(server, routes, journal)
    first.poll()
    failed = first.pending["escrow:tick"]["run_id"]
    server.states[failed] = "failed"
    recovered = PersistentScheduler(server, routes, journal)
    recovered.poll()
    assert recovered.failures[failed]["state"] == "failed"
    replacement = recovered.pending["escrow:tick"]["run_id"]
    assert replacement != failed
    assert len(server.admissions) == 6  # four inboxes, failed tick, replacement tick
    again = PersistentScheduler(server, routes, journal)
    again.poll()
    assert len(server.admissions) == 6
    assert failed in again.failures
    assert again.pending["escrow:tick"]["run_id"] == replacement


def test_dashboard_queries_use_the_separate_readonly_client(tmp_path: Path) -> None:
    def read(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer readonly-test"
        return httpx.Response(200, json={"result": '{"deals":[]}'})

    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Dashboard query used admission credentials")

    tenant = "00000000-0000-4000-8000-000000000001"
    reader = AgentDbClient(
        "http://localhost:18180",
        "readonly-test",
        tenant,
        transport=httpx.MockTransport(read),
    )
    scheduler = AgentDbClient(
        "http://localhost:18180",
        "scheduler-test",
        tenant,
        transport=httpx.MockTransport(forbidden),
    )
    engine = AgentDbEngine(scheduler, {}, tmp_path, reader=reader)
    try:
        assert engine.source.deals() == []
    finally:
        engine.close()
