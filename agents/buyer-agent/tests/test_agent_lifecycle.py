"""Reference agent shutdown and health wiring tests."""

from __future__ import annotations

import pytest

from buyer_agent import Agent
from buyer_agent.session_store import SessionStore


@pytest.mark.asyncio
async def test_shutdown_clears_session_store() -> None:
    store = SessionStore(sessions={"session-1": "active"})
    agent = Agent()
    agent.dependencies = agent.dependencies.__class__(
        records=agent.dependencies.records,
        functions=agent.dependencies.functions,
        session_store=store,
        closeables=(store,),
    )
    assert agent.health()["sessions"] == 1

    await agent.shutdown()
    assert store.sessions == {}
    assert agent.health()["sessions"] == 0
