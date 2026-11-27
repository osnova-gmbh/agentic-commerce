"""Lifecycle cleanup tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from seller_agent.lifecycle import (
    Closeable,
    close_all,
)


@dataclass
class _SyncCloseable:
    label: str
    order: list[str] = field(default_factory=list)

    def close(self) -> None:
        self.order.append(self.label)


@dataclass
class _AsyncCloseable:
    label: str
    order: list[str] = field(default_factory=list)

    async def close(self) -> None:
        self.order.append(self.label)


@dataclass
class _FailingCloseable:
    label: str
    order: list[str] = field(default_factory=list)

    def close(self) -> None:
        self.order.append(self.label)
        raise RuntimeError(self.label)


@pytest.mark.asyncio
async def test_close_all_closes_in_reverse_order() -> None:
    order: list[str] = []
    resources: tuple[Closeable, ...] = (
        _SyncCloseable("first", order),
        _AsyncCloseable("second", order),
        _SyncCloseable("third", order),
    )

    await close_all(resources)
    assert order == ["third", "second", "first"]


@pytest.mark.asyncio
async def test_close_all_attempts_every_resource_before_raising() -> None:
    order: list[str] = []
    resources: tuple[Closeable, ...] = (
        _FailingCloseable("first", order),
        _SyncCloseable("second", order),
        _FailingCloseable("third", order),
    )

    with pytest.raises(ExceptionGroup) as exc_info:
        await close_all(resources)

    assert order == ["third", "second", "first"]
    assert [str(exc) for exc in exc_info.value.exceptions] == ["third", "first"]
