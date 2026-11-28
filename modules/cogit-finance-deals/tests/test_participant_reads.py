"""A shared company is not enough: the installation must own a party's DID."""

from typing import Any

import pytest
from cogit_finance_seams import ModuleError
from deals_kit import MODULE


def test_another_installation_in_the_buyers_company_cannot_read(
    host: Any, deals: Any
) -> None:
    # Identity rows represent the authoritative messaging-module binding.
    host.db.execute(
        "CREATE TABLE msg_agent_identities (did TEXT, installation_id TEXT, org_id TEXT, active INTEGER)"
    )
    host.db.executemany(
        "INSERT INTO msg_agent_identities VALUES (?, ?, ?, 1)",
        [
            ("did:key:buyer", "buyer-agent", "buyer-co"),
            ("did:key:other", "other-buyer-agent", "buyer-co"),
            ("did:key:seller", "seller-agent", "seller-co"),
        ],
    )
    deals.commit(
        "service_request",
        "REQUESTED",
        body={"envelope": {"sender_did": "did:key:buyer"}},
        outbox=[
            {
                "outbox_id": "request-relay",
                "envelope": {"recipient_did": "did:key:seller"},
            }
        ],
    )
    for state in ("REQUESTED", "QUOTED"):
        if state == "QUOTED":
            deals.commit(
                "terms_proposed",
                state,
                deal={
                    "terms": {
                        "buyer_did": "did:key:buyer",
                        "seller_did": "did:key:seller",
                    }
                },
            )
        for participant in ("buyer-agent", "seller-agent"):
            assert (
                host.port(participant).module_query(
                    MODULE, "deal.read", {"deal_id": "deal-1"}
                )["deal"]["state"]
                == state
            )
        other = host.port("other-buyer-agent")
        with pytest.raises(ModuleError, match="forbidden"):
            other.module_query(MODULE, "deal.read", {"deal_id": "deal-1"})
        assert other.module_query(MODULE, "deal.list") == {"deals": []}
        assert other.module_query(MODULE, "ledger.balances")["held"] == 0
