param(
    [string]$Tag = "cogit-finance:local"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
docker build --tag $Tag $Root
