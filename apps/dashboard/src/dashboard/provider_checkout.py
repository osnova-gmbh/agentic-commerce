"""Local escrow simulations tied to the selected public provider offering.

The public companies remain unverified prospects. The already configured local
seller agent simulates a purchase of their offering; it does not act for them.
"""

from __future__ import annotations

import io
import json
import zipfile

from .catalog import public_offer

FILES = ["delivery.md", "license.json", "summary.json"]


def provider_services(companies: list[dict], maximum: int) -> tuple[dict[str, dict], list[dict]]:
    metadata, offers = {}, []
    for company in companies:
        for published in (company.get("profile") or {}).get("offers", []):
            public = public_offer(company, published)
            offer_id = f"provider:{company['org_id']}:{public['offer_id']}"
            amount = public["price_minor"]
            positive = type(amount) is int and amount > 0 and public["currency"] == "EUR"
            suggested = amount if positive and amount <= maximum else min(50000, maximum)
            metadata[offer_id] = {
                "provider_company_id": company["org_id"],
                "provider_offer_id": public["offer_id"],
                "provider_company_name": public["company_name"],
                "provider_demo": True,
                "seller_name": public["company_name"],
                "simulation_seller_name": "Example Seller GmbH (local simulation)",
                "published_price_minor": amount,
                "published_currency": public["currency"],
                "published_price_label": public["price_label"],
                "pricing_basis": public["pricing_basis"],
                "source_url": public["source_url"],
                "availability": public["availability"],
                "requires_demo_amount": not positive,
                "suggested_demo_price_minor": suggested,
                "demo_max_price_minor": maximum,
            }
            offers.append({
                "offer_id": offer_id,
                "title": public["title"],
                "description": public["description"],
                "category": "provider-simulation",
                "price_minor": suggested,
                "currency": "EUR",
                "delivery_time_s": 900,
                "input_schema": {
                    "type": "object",
                    "properties": {"brief": {
                        "type": "string", "minLength": 1, "maxLength": 2000,
                        "title": "Purchase brief", "default": f"Evaluate {public['title']} for our team.",
                    }},
                    "required": ["brief"], "additionalProperties": False,
                },
                "deliverable": {"media_type": "application/zip", "required_files": FILES},
                "default_acceptance": {
                    "policy": "all", "max_attempts": 2,
                    "evaluators": [
                        {"evaluator_id": "integrity", "version": 1, "params": {}},
                        {"evaluator_id": "required-files", "version": 1, "params": {"required_files": FILES}},
                        {"evaluator_id": "deadline", "version": 1, "params": {}},
                    ],
                },
                "active": True,
            })
    return metadata, offers


def provider_delivery(deal_id: str, service: dict, inputs: dict, *, complete: bool) -> bytes:
    """A reproducible simulated delivery containing the exact selected offer."""
    detail = {
        "deal_id": deal_id, "offer_id": service["provider_offer_id"],
        "provider_company_id": service["provider_company_id"],
        "provider_name": service["provider_company_name"], "product": service["title"],
        "brief": inputs["brief"], "simulated": True,
        "notice": "Local demonstration only. No vendor order or real license was issued.",
    }
    files = {
        "delivery.md": (
            f"# {service['title']} — simulated delivery\n\n"
            f"Provider offering: {service['provider_company_name']}\n\n"
            f"Purchase brief: {inputs['brief']}\n\n"
            f"Deal: {deal_id}\n\n"
            "This local escrow demonstration does not purchase or provision a real vendor service.\n"
        ),
        "license.json": json.dumps({**detail, "license_type": "simulation-only"}, indent=2, sort_keys=True),
        "summary.json": json.dumps(detail, indent=2, sort_keys=True),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            if name == "summary.json" and not complete:
                continue
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return buffer.getvalue()
