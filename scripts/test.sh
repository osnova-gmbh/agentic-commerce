#!/usr/bin/env bash
# Run the test suite of every plain Python package, one pytest process per package,
# then the end-to-end tests. Pass directories to run only those.
set -uo pipefail
cd "$(dirname "$0")/.."
root="$(pwd)"
python_path="$root/.venv/bin/python"
if [ ! -f "$python_path" ]; then python_path="$root/.venv/Scripts/python.exe"; fi
if [ ! -f "$python_path" ]; then
  echo "No root virtual environment found; run bash scripts/dev-install.sh first." >&2
  exit 1
fi
targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
  for dir in packages/cogit-finance-seams packages/cogit-messaging-shim modules/* apps/*; do
    if [ -f "$dir/pyproject.toml" ] && [ -d "$dir/tests" ] && [ ! -f "$dir/cogit.yaml" ]; then targets+=("$dir"); fi
  done
  if compgen -G "tests/e2e/test_*.py" >/dev/null; then targets+=("tests/e2e"); fi
fi
failed=0
for dir in "${targets[@]}"; do
  echo "=== $dir"
  (cd "$dir" && "$python_path" -m pytest -q) || failed=1
done
exit $failed
