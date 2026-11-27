# pyright: basic
"""The seller's offers file: what it publishes and what it quotes from.

The file has the shape of the ``catalog.publish`` arguments: ``seller_org_id`` and
``offers``. Without a path the copy of ``data/demo/offers.seller-co.yaml`` packaged
with the agent is read.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from cogit_messaging_shim import canonical_bytes

PACKAGED_OFFERS = "offers.seller-co.yaml"


def load_catalog(path: str | None = None) -> dict[str, Any]:
    """Read the offers file; return ``{"seller_org_id": ..., "offers": [...]}``."""
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        packaged = resources.files("seller_agent").joinpath("data", PACKAGED_OFFERS)
        text = packaged.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("offers"), list):
        raise ValueError("The offers file must be a mapping with a list of offers")
    for offer in data["offers"]:
        if not isinstance(offer, dict) or not offer.get("offer_id"):
            raise ValueError("Every offer needs an offer_id")
    canonical_bytes(data["offers"])  # JSON only, no floats: raises TypeError otherwise
    return {"seller_org_id": data.get("seller_org_id"), "offers": data["offers"]}


def find_offer(offers: list[dict[str, Any]], offer_id: Any) -> dict[str, Any] | None:
    """The active offer with this ID, or ``None``."""
    for offer in offers:
        if offer.get("offer_id") == offer_id and offer.get("active", True):
            return offer
    return None
