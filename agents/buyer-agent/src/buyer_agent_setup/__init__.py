"""Host composition entry point, separate from the resident agent domain."""

from .cli import main
from .manifest import configured_agent, read_manifest, resolved_manifest, write_manifest

__all__ = [
    "configured_agent",
    "main",
    "read_manifest",
    "resolved_manifest",
    "write_manifest",
]
