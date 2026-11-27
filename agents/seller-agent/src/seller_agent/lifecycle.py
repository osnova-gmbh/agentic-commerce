"""Deterministic closeable resource cleanup."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Closeable(Protocol):
    """Resource that can release external handles synchronously or asynchronously."""

    def close(self) -> Awaitable[None] | None: ...


async def close_all(resources: tuple[Closeable, ...]) -> None:
    """Close resources in reverse construction order, raising after all attempts."""

    failures: list[Exception] = []
    for resource in reversed(resources):
        try:
            await _close_one(resource)
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise ExceptionGroup("one or more resources failed to close", failures)


async def _close_one(resource: Closeable) -> None:
    result = resource.close()
    if inspect.isawaitable(result):
        await result
