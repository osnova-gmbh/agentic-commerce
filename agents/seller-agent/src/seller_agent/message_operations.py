# pyright: basic
"""The seller's operations: the seller core on a Cogit run handle.

The core is built for each run from the run handle and the environment:

- ``AGENT_KEY_FILE``: the agent's signing key, created on first use; the default
  is ``.state/keys/seller-agent.key``;
- ``ESCROW_DID``: E's DID; without it the DID is resolved with ``identity.resolve``;
- ``SELLER_OFFERS_FILE``: the offers file; the default is the packaged copy of
  ``data/demo/offers.seller-co.yaml``;
- ``SELLER_ORG_ID``: the seller's org; the default is the offers file's
  ``seller_org_id``, then ``seller-co``;
- ``SELLER_MODE``: ``ok`` (default) or ``broken`` (attempt 1 lacks ``summary.json``);
- ``SELLER_DELAY_S``: seconds to wait before the first delivery, default ``0``.
"""

from __future__ import annotations

import os
from typing import Any

from cogit_agent_sdk import OperationInvocation
from cogit_finance_seams import ModulePort
from cogit_finance_seams.cogit_host import HandleArtifacts, HandleModules
from cogit_messaging_shim import MESSAGING_MODULE, AgentKey, ShimMessaging

from seller_agent.offers import load_catalog
from seller_agent.identity import identity
from seller_agent.schemas import (
    HandleMessageInput,
    HandleMessageOutput,
    PublishCatalogInput,
    PublishCatalogOutput,
)
from seller_agent.seller import SellerCore, publish_offers
from seller_agent.service_delivery import build_agreed_delivery

AGENT_ID = "seller-agent"
DEFAULT_ORG_ID = "seller-co"


def load_key() -> AgentKey:
    """The agent's signing key; the file is created on first use."""
    return identity.load_key()


def resolve_escrow_did(modules: ModulePort) -> str:
    """E's DID from ``ESCROW_DID``, otherwise from the messaging module."""
    configured = os.environ.get("ESCROW_DID")
    if configured:
        return configured
    answer = modules.module_query(
        MESSAGING_MODULE, "identity.resolve", {"role": "escrow"}
    )
    identity = answer.get("identity")
    if not identity:
        raise RuntimeError("ESCROW_DID is not set and no escrow identity is registered")
    return str(identity["did"])


def load_offers() -> tuple[str, list[dict[str, Any]]]:
    """The seller's org and offers from the offers file and the environment."""
    catalog = load_catalog(os.environ.get("SELLER_OFFERS_FILE") or None)
    org_id = os.environ.get("SELLER_ORG_ID") or catalog["seller_org_id"]
    return str(org_id or DEFAULT_ORG_ID), catalog["offers"]


def build_core(handle: Any) -> SellerCore:
    """Build the seller core over the run handle's module and artifact seams."""
    modules = HandleModules(handle)
    seller_org_id, offers = load_offers()
    key = load_key()
    escrow_did = resolve_escrow_did(modules)
    return SellerCore(
        modules=modules,
        artifacts=HandleArtifacts(handle),
        messaging=ShimMessaging(key, modules),
        escrow_did=escrow_did,
        seller_org_id=seller_org_id,
        offers=offers,
        mode=(os.environ.get("SELLER_MODE") or "ok").strip().lower(),
        delay_s=float(os.environ.get("SELLER_DELAY_S") or 0),
        build_delivery=lambda deal_id, complete: build_agreed_delivery(
            modules, deal_id, complete, escrow_did=escrow_did,
            seller_did=key.did, seller_org_id=seller_org_id, offers=offers,
        ),
    )


def publish_catalog(
    request: PublishCatalogInput,
    invocation: OperationInvocation,
) -> PublishCatalogOutput:
    """Publish the offers file to the catalog module."""
    del request
    with invocation.handle.step("action", "publish_catalog"):
        # Publishing needs neither the signing key nor E's DID, so it also works
        # before the identities are registered.
        seller_org_id, offers = load_offers()
        count = publish_offers(
            HandleModules(invocation.handle),
            seller_org_id,
            offers,
            invocation.idempotency_key,
        )
    return PublishCatalogOutput(count=count)


def handle_message(
    request: HandleMessageInput,
    invocation: OperationInvocation,
) -> HandleMessageOutput:
    """Handle one finance message from E: quote, accept terms, deliver, redeliver."""
    with invocation.handle.step("action", "handle_message"):
        result = build_core(invocation.handle).handle_message(request.envelope)
    return HandleMessageOutput.model_validate(result)
