param(
    [switch]$SkipSync,
    [switch]$SkipImage
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python scripts/verify_framework_wheels.py
if (-not $SkipSync) {
    uv lock --check
    uv sync --all-extras --frozen --no-editable
    uv pip check
    uv run --no-sync python -I scripts/verify_installed_packages.py
}

uv run --no-sync python scripts/validate_manifest.py
uv run --no-sync python scripts/export_action_contract.py --output action-contract.v1.json
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync lint-imports
uv run --no-sync deptry .
uv run --no-sync python -I -m pytest -o pythonpath=tests --import-mode=importlib

if (-not $SkipImage) {
    & (Join-Path $Root "scripts\build_image.ps1")
}

Write-Host "All reference-agent checks passed."
