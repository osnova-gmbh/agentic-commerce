"""Idempotent bootstrap of the local AgentDb commerce demonstration."""

import hashlib
import json
import os
from pathlib import Path

import yaml
from cogit_agent_sdk import OperationInvocation, bind_action, operation
from cogit_finance_seams.cogit_host import HandleModules
from pydantic import BaseModel


class BootstrapInput(BaseModel):
    pass


class BootstrapOutput(BaseModel):
    companies: int
    identities: int
    evaluators: int


def bootstrap(
    request: BootstrapInput, invocation: OperationInvocation
) -> BootstrapOutput:
    del request
    data = Path(os.environ["COGIT_COMMERCE_DATA_DIR"])
    identities = json.loads(
        Path(os.environ["COGIT_COMMERCE_IDENTITIES_FILE"]).read_text(encoding="utf-8")
    )
    modules = HandleModules(invocation.handle)

    def write(module, export, payload):
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        return modules.module_command(
            module, export, payload, idempotency_key=f"bootstrap:{export}:{digest}"
        )

    for identity in identities.values():
        write("cogit-messaging", "identity.register", identity)
    companies = yaml.safe_load((data / "companies.yaml").read_text(encoding="utf-8"))[
        "companies"
    ]
    for company in companies:
        write("cogit-finance-catalog", "company.upsert", {"company": company})
    evaluators = yaml.safe_load((data / "evaluators.yaml").read_text(encoding="utf-8"))[
        "evaluators"
    ]
    for evaluator in evaluators:
        evaluator = {**evaluator, "did": identities["evaluator-agent"]["did"]}
        write("cogit-finance-catalog", "evaluator.upsert", {"evaluator": evaluator})
    return BootstrapOutput(
        companies=len(companies), identities=len(identities), evaluators=len(evaluators)
    )


def bootstrap_binding():
    return bind_action(
        operation(bootstrap),
        name="bootstrap",
        description="Seed configured local demo identities, companies and evaluators once.",
        risk="write",
        idempotency="inherent",
    )
