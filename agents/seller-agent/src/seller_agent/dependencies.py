"""Dependency assembly kept separate from runtime transport wiring."""

from dataclasses import dataclass

from cogit_agent_sdk import FunctionRegistry

from seller_agent.domain import RecordService
from seller_agent.lifecycle import Closeable
from seller_agent.session_store import SessionStore


@dataclass(frozen=True)
class AgentDependencies:
    records: RecordService
    functions: FunctionRegistry
    session_store: SessionStore
    closeables: tuple[Closeable, ...]


def build_dependencies(
    *,
    session_store: SessionStore | None = None,
) -> AgentDependencies:
    """Build synthetic read services and process resources."""

    registry = FunctionRegistry()
    registry.load_package("seller_agent.functions")
    store = session_store or SessionStore()
    return AgentDependencies(
        records=RecordService(),
        functions=registry,
        session_store=store,
        closeables=(store,),
    )
