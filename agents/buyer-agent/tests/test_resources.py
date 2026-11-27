"""Prompt resource loading tests."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from cogit_runtime.manifest import load_manifest

from buyer_agent.resources import load_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_prompts_load_from_package_resources() -> None:
    prompt = load_prompt("system.md")
    assert prompt.strip()
    assert load_manifest(ROOT / "cogit.yaml").descriptor.name in prompt


def test_prompt_assets_ship_in_wheel_package() -> None:
    package_name = "buyer_agent"
    package = resources.files(package_name).joinpath("prompts")
    names = {path.name for path in package.iterdir()}
    assert "system.md" in names
