#!/bin/sh
set -eu

: "${COGIT_AGENTDB_COHORT_RECEIPT:?Mount the published deployment receipt and set COGIT_AGENTDB_COHORT_RECEIPT}"
: "${COGIT_AGENTDB_INSTALLATION_ID:?Set the published installation ID}"
: "${COGIT_AGENTDB_POOL_ID:?Set the published pool ID}"
: "${COGIT_AGENTDB_URL:?Set the AgentDb API origin}"
: "${COGIT_AGENTDB_API_VERSION:?Set the AgentDb API version}"
: "${COGIT_AGENTDB_WORKER_TOKEN:?Set the scoped pool worker token}"
if [ "${COGIT_DEV_MODE:-0}" != 0 ]; then
    echo "Canonical AgentDb workers require COGIT_DEV_MODE=0" >&2
    exit 1
fi

manifest="${1:-/app/worker-cohort/cogit.yaml}"
exec python -I -B -m cogit_runtime work --manifest "$manifest"
