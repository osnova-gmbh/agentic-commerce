"""Minimal in-process session scratch storage for lifecycle demos."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionStore:
    """Process-local session map cleared during agent shutdown."""

    sessions: dict[str, str] = field(default_factory=dict[str, str])

    def close(self) -> None:
        self.sessions.clear()
