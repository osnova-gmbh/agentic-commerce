#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && cd .. && pwd)"
cd "$ROOT"

SKIP_SYNC=false
SKIP_IMAGE=false
for arg in "$@"; do
  case "$arg" in
    --skip-sync) SKIP_SYNC=true ;;
    --skip-image) SKIP_IMAGE=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

python scripts/verify_framework_wheels.py
if [ "$SKIP_SYNC" = false ]; then
  uv lock --check
  uv sync --all-extras --frozen --no-editable
  uv pip check
  uv run --no-sync python -I scripts/verify_installed_packages.py
fi

uv run --no-sync python scripts/validate_manifest.py
uv run --no-sync python scripts/export_action_contract.py --output action-contract.v1.json
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync lint-imports
uv run --no-sync deptry .
uv run --no-sync python -I -m pytest -o pythonpath=tests --import-mode=importlib

if [ "$SKIP_IMAGE" = false ]; then
  bash scripts/build_image.sh
fi

echo "All reference-agent checks passed."
