"""Public response contracts and executable checkout affordances."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

JsonObject = dict[str, Any]

class PublicModel(BaseModel):
    model_config = ConfigDict(extra="allow")

class APIError(PublicModel):
    error: str
    message: str
    details: list[JsonObject] | None = None

class RequiredHeader(PublicModel):
    name: str
    required: bool = True
    description: str
    schema_: JsonObject = Field(alias="schema")

class IdempotencyPolicy(PublicModel):
    required: bool
    header: str | None = None
    replay: str

class ActionDescriptor(PublicModel):
    name: str
    method: Literal["GET", "POST"]
    href: str
    input_schema: JsonObject
    response_schema: JsonObject
    required_headers: list[RequiredHeader] = Field(default_factory=list)
    idempotency: IdempotencyPolicy
    side_effects: list[str]
    preconditions: list[str]
    requires_confirmation: bool

class PublicOffer(PublicModel):
    company_id: str
    company_name: str
    offer_id: str
    title: str
    description: str
    category: str
    source_url: str
    price_minor: int | None
    currency: str | None
    price_label: str
    pricing_basis: str | None
    contact_url: str | None
    availability: str
    verified_on: str | date | None

class PublicCompany(PublicModel):
    org_id: str
    name: str
    roles: list[str]
    categories: list[str]
    website: str | None
    products_and_services: str
    target_customers: str
    campus: str | None
    programme: str | None
    status: str | None
    outreach_priority: int | None
    recommended: bool
    offers: list[PublicOffer]

class CatalogResponse(PublicModel):
    companies: list[PublicCompany]

class ProviderOffersResponse(PublicModel):
    offers: list[PublicOffer]

class Deliverable(PublicModel):
    media_type: str
    required_files: list[str]

class Service(PublicModel):
    seller_org_id: str
    offer_id: str
    title: str
    description: str
    category: str
    price_minor: int | None = Field(description="EUR minor units for the demo quote; null requires an explicit amount.")
    currency: str
    delivery_time_s: int
    input_schema: JsonObject = Field(description="JSON Schema for inputs sent when preparing this offer.")
    deliverable: Deliverable
    default_acceptance: JsonObject
    active: bool
    seller_name: str
    demo: bool
    price: str
    payout_minor: int | None
    fee_minor: int | None
    fee_bps: int
    payout: str
    fee: str
    actions: list[ActionDescriptor] = Field(default_factory=list)

class ServiceListResponse(PublicModel):
    services: list[Service]

class DealSummary(PublicModel):
    deal_id: str
    state: str
    tone: str
    buyer_org_id: str
    seller_org_id: str
    offer_id: str
    head_seq: int
    price_minor: int | None
    currency: str
    price: str
    created_at: str
    updated_at: str
    updated_time: str
    offer_title: str | None = None

class DealsResponse(PublicModel):
    deals: list[DealSummary]

class DealStep(PublicModel):
    n: int
    key: str
    label: str
    status: str
    note: str

class MoneyTile(PublicModel):
    key: str
    label: str
    amount_minor: int
    display: str

class DealMoney(PublicModel):
    phase: str
    headline: str
    detail: str
    tiles: list[MoneyTile]

class EvaluatorVerdict(PublicModel):
    evaluator: str
    version: int | None
    outcome: str
    reasons: list[str]

class DeliveryAttempt(PublicModel):
    attempt: int
    delivery_id: str
    delivered_at: str
    decision: str | None
    reasons: list[str]
    verdicts: list[EvaluatorVerdict]

class TimelineEvent(PublicModel):
    seq: int
    event_type: str
    detail: str
    actor: str
    actor_did: str
    state_after: str
    hash8: str
    time: str
    tone: str

class DealViewResponse(PublicModel):
    deal: DealSummary
    steps: list[DealStep]
    money: DealMoney
    attempts: list[DeliveryAttempt]
    timeline: list[TimelineEvent]

class BalanceAmounts(PublicModel):
    held: int
    seller: int
    fee: int
    buyer_refund: int
    returned: int

class BalancesResponse(PublicModel):
    deal_id: str | None
    balances: BalanceAmounts
    display: dict[str, str]

class BankAccount(PublicModel):
    iban: str
    owner: str
    balance_minor: int
    balance: str

class AccountsResponse(PublicModel):
    accounts: list[BankAccount]

class HealthResponse(PublicModel):
    status: str

class BorisEvidenceEvent(PublicModel):
    event_id: str
    agent_id: str
    deal_id: str
    message_id: str
    type_key: str
    request_id: str
    started_at: str
    completed_at: str | None
    status: Literal["pending", "verified", "failed"]
    request_sha256: str
    response_sha256: str | None
    endpoint: str | None = None
    sender_did: str | None = None
    transport_kind: str
    error: str | None

class BorisEvidenceSummary(PublicModel):
    pending: int
    verified: int
    failed: int

class BorisReportResponse(PublicModel):
    mode: str
    transport_kind: str
    configured: bool
    endpoint: str | None
    deal_id: str | None
    events: list[BorisEvidenceEvent]
    summary: BorisEvidenceSummary
    error: str | None = None
    execution_location: str

class CheckoutOrder(PublicModel):
    service: Service
    inputs: JsonObject
    scenario: str

class CheckoutPayment(PublicModel):
    price: str
    payout: str
    fee: str
    to_iban: str

class CheckoutStatusResponse(PublicModel):
    running: bool
    deal_id: str | None
    scenario: str | None
    error: str | None
    mode: str
    server_busy: bool | None = None
    active_deal_id: str | None = None
    state: str | None
    order: CheckoutOrder | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    actions: list[ActionDescriptor] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    terms: JsonObject | None = None
    payment: CheckoutPayment | None = None
    boris: BorisReportResponse

class CheckoutMutationResponse(PublicModel):
    deal_id: str
    action: str
    status: Literal["processing"]
    links: dict[str, str] = Field(default_factory=dict)

class LegacyPurchaseResponse(PublicModel):
    status: str
    sellers_seen: int
    offers_seen: int
    deal_id: str | None
    seller_org_id: str | None
    offer_id: str | None
    scenario: str

class DiscoveryOperation(PublicModel):
    name: str
    method: str
    href: str
    summary: str
    description: str
    input_schema: JsonObject
    required_headers: list[RequiredHeader]
    parameters: list[JsonObject]
    responses: dict[str, JsonObject]
    side_effects: list[str]
    requires_confirmation: bool

class DiscoveryResponse(PublicModel):
    name: str
    version: str
    api_base: str
    mode: Literal["local-simulation", "read-only"]
    description: str
    authentication: dict[str, str]
    links: dict[str, str]
    operations: list[DiscoveryOperation]
    workflow: list[str]
    safety: JsonObject
