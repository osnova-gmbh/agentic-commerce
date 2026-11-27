"""Admit typed queue work with the generated client and wait for durable outcome."""

from __future__ import annotations

import argparse
import os
import time
from hashlib import sha256
from uuid import UUID

from agentdb_client import ApiClient, Configuration
from agentdb_client.api.client_api import ClientApi
from agentdb_client.exceptions import ApiException
from agentdb_client.models.accept_query_request import AcceptQueryRequest
from agentdb_client.models.accept_query_request_input import AcceptQueryRequestInput
from agentdb_client.models.allocate_artifact_upload_request import (
    AllocateArtifactUploadRequest,
)
from agentdb_client.models.finalize_artifact_upload_request import (
    FinalizeArtifactUploadRequest,
)
from pydantic import ValidationError

from evaluator_agent.database_example import (
    PersistRequestInput,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-id", required=True, type=UUID)
    parser.add_argument("--request-id", default="request-db")
    parser.add_argument("--description", default="Persist a reference record.")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 600:
        parser.error("timeout must be between 0 and 600 seconds")
    try:
        request = PersistRequestInput(
            request_id=args.request_id, description=args.description
        )
    except ValidationError:
        parser.error(
            "request ID and description must satisfy the reference input contract"
        )
    request_id = request.request_id
    if request_id is None:
        raise ValueError("typed request did not produce a request ID")
    try:
        config = Configuration(
            host=os.environ["COGIT_AGENTDB_URL"],
            access_token=os.environ["AGENTDB_CLIENT_TOKEN"],
        )
        config.retries = 0
        with ApiClient(config) as transport:
            client = ClientApi(transport)
            key = "reference-run:" + sha256(request_id.encode("utf-8")).hexdigest()
            input_text = request.model_dump_json()
            input_bytes = input_text.encode("utf-8")
            input_sha = sha256(input_bytes).hexdigest()
            upload = client.allocate_artifact_upload(
                idempotency_key=key + ":input",
                allocate_artifact_upload_request=AllocateArtifactUploadRequest(
                    mediaType="application/json",
                    classification="internal",
                    sha256=input_sha,
                    byteLength=len(input_bytes),
                ),
                _request_timeout=10.0,
            )
            client.put_artifact_upload_content(
                upload.upload_id, input_bytes, _request_timeout=10.0
            )
            client.finalize_artifact_upload(
                upload.upload_id,
                idempotency_key=key + ":input:finalize",
                finalize_artifact_upload_request=FinalizeArtifactUploadRequest(
                    sha256=input_sha, byteLength=len(input_bytes)
                ),
                _request_timeout=10.0,
            )
            accepted = client.accept_query(
                idempotency_key=key,
                accept_query_request=AcceptQueryRequest(
                    installationId=args.installation_id,
                    input=AcceptQueryRequestInput.from_dict(
                        {"text": input_text, "sha256": input_sha}
                    ),
                ),
                _request_timeout=10.0,
            )
            print(f"Admitted AgentDb run {accepted.run_id}; waiting for its outcome.")
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                run = client.get_run(accepted.run_id, _request_timeout=10.0)
                if run.lifecycle in ("succeeded", "failed", "cancelled"):
                    print(
                        client.get_run_events(
                            accepted.run_id, limit=100, _request_timeout=10.0
                        ).to_json()
                    )
                    print(
                        client.get_run_result(
                            accepted.run_id, _request_timeout=10.0
                        ).to_json()
                    )
                    return 0 if run.lifecycle == "succeeded" else 1
                time.sleep(0.5)
    except KeyError:
        parser.exit(
            1, "Set COGIT_AGENTDB_URL and AGENTDB_CLIENT_TOKEN from your deployment.\n"
        )
    except (ApiException, OSError):
        # Authentication headers and server response bodies may contain private data.
        parser.exit(
            1, "AgentDb request failed; inspect authorized service/run status.\n"
        )
    parser.exit(1, "Run is still nonterminal; inspect its AgentDb status and events.\n")


if __name__ == "__main__":
    raise SystemExit(main())
