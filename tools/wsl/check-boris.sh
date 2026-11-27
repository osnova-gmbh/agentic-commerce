#!/bin/sh
# Read-only check of the Boris (Affinidi) CLI and the WSL prerequisites.
# Run from PowerShell:
#   wsl -d Ubuntu -u denys --exec /bin/sh /mnt/c/ai/_experiments/agentic-commerce/tools/wsl/check-boris.sh
# Writes tools/wsl/boris-check.out.txt next to this script. Prints no credentials.
OUT="$(dirname "$0")/boris-check.out.txt"
BORIS=/home/denys/.boris/bin/boris
{
  echo "# boris check $(date -u +%Y-%m-%dT%H:%M:%SZ) as $(id -un)"
  echo "## uname"; uname -srm
  echo "## boris --version"; "$BORIS" --version 2>&1
  echo "## boris doctor"; "$BORIS" doctor --plain --no-color 2>&1
  echo "## boris status"; "$BORIS" status --json --no-input 2>&1
  echo "## boris local status"; "$BORIS" local status --json --no-input 2>&1
  echo "## boris agent status"; "$BORIS" agent status --json --no-input 2>&1
  echo "## boris help (top level)"; "$BORIS" --help 2>&1 | head -60
  echo "## boris agent --help"; "$BORIS" agent --help 2>&1 | head -60
  echo "## docker version (as denys)"; docker version --format '{{.Server.Version}}' 2>&1 | head -3
  echo "## secret service on dbus"; (busctl --user list 2>/dev/null | grep -i secrets) || echo "no org.freedesktop.secrets"
  echo "## linger"; loginctl show-user "$(id -un)" -p Linger 2>&1
  echo "## python / uv"; python3 --version 2>&1; (uv --version 2>&1 || echo "uv not found")
} > "$OUT" 2>&1
echo "wrote $OUT"
