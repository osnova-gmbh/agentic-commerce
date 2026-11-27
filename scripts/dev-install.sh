#!/usr/bin/env bash
# Create .venv at the repository root and install every plain Python package of this
# repository in editable mode. Cogit agent projects keep their own environments
# (cogit install --project <dir>); their sources join the root tests through pythonpath.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then uv venv --quiet .venv; fi
python_path=".venv/bin/python"
if [ ! -f "$python_path" ]; then python_path=".venv/Scripts/python.exe"; fi
args=()
for dir in packages/cogit-finance-seams packages/cogit-messaging-shim modules/* apps/*; do
  if [ -f "$dir/pyproject.toml" ] && [ ! -f "$dir/cogit.yaml" ]; then args+=(-e "$dir"); fi
done
uv pip install --quiet --python "$python_path" "${args[@]}" pytest httpx pyyaml jsonschema
# Framework cohort for the offline end-to-end tests: taken from the first vendored set found.
wheels="${COGIT_WHEELS_DIR:-}"
if [ -z "$wheels" ]; then
  for candidate in packages/cogit-finance/vendor/wheels agents/*/vendor/wheels; do
    if [ -d "$candidate" ]; then wheels="$candidate"; break; fi
  done
fi
if [ -n "$wheels" ] && [ -d "$wheels" ]; then
  uv pip install --quiet --python "$python_path" \
    "$wheels/cogit_agent_sdk-0.5.16-py3-none-any.whl" \
    "$wheels/cogit_tool_core-0.1.3-py3-none-any.whl" \
    "$wheels/agentdb_client-0.2.13-py3-none-any.whl" \
    "$wheels/cogit_runtime-0.3.31-py3-none-any.whl"
  echo "installed the Cogit cohort from $wheels"
else
  echo "no vendored Cogit wheels found; SDK-dependent tests will be skipped"
fi
echo "ready: .venv"
