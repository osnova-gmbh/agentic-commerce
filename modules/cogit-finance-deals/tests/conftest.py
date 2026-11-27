from __future__ import annotations

import pytest
from cogit_finance_deals_module import DealsModule
from cogit_finance_seams import LocalModuleHost
from deals_kit import Clock, Deals


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def host(clock: Clock) -> LocalModuleHost:
    host = LocalModuleHost(clock=clock)
    host.install(DealsModule())
    return host


@pytest.fixture()
def deals(host: LocalModuleHost, clock: Clock) -> Deals:
    return Deals(host, clock)
