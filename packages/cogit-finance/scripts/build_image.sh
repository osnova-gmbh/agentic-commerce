#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && cd .. && pwd)"
TAG="${1:-cogit-finance:local}"
docker build --tag "$TAG" "$ROOT"
