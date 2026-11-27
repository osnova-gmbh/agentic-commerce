"""Package resource loading for prompt assets."""

from __future__ import annotations

from importlib import resources


def load_prompt(name: str) -> str:
    """Load a prompt markdown file bundled with the package."""

    normalized = name.removesuffix(".md")
    package_name = "seller_agent"
    package = resources.files(package_name).joinpath("prompts")
    return (package / f"{normalized}.md").read_text(encoding="utf-8")
