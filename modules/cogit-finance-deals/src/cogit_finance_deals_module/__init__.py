"""Reference implementation of the cogit-finance-deals AgentDb module."""

from .module import DEFAULT_ESCROW_INSTALLATION_ID, MIGRATIONS_DIR, DealsModule
from .rows import ACCOUNTS, INTENT_KINDS, INTENT_STATUSES, ZERO_HASH

__all__ = [
    "ACCOUNTS",
    "DEFAULT_ESCROW_INSTALLATION_ID",
    "INTENT_KINDS",
    "INTENT_STATUSES",
    "MIGRATIONS_DIR",
    "ZERO_HASH",
    "DealsModule",
]
