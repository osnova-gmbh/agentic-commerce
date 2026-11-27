"""E's business logic: a pure domain and a core that works over ports.

Domain (no I/O): ``transitions`` (SPEC §5.2 as data), ``guards``, ``terms``,
``money``, ``policy``, ``ids``, ``messages``, ``view``, ``schema_check``.
Core: ``EscrowCore`` with ``handle_message`` and ``tick``.
"""

from cogit_finance.escrow.core import EscrowCore
from cogit_finance.escrow.reasons import Rejected

__all__ = ["EscrowCore", "Rejected"]
