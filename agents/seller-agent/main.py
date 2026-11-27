"""ASGI entry point used by local tooling and container platforms."""

from pathlib import Path

from cogit_runtime import CogitRuntimeApp

from seller_agent import Agent

ROOT = Path(__file__).resolve().parent

runtime = CogitRuntimeApp.from_manifest(
    ROOT / "cogit.yaml",
    agent_class=Agent,
)
app = runtime.build()
