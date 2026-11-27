param([string]$RequestId = "request-client")
$ErrorActionPreference = "Stop"
if (-not $env:COGIT_AGENTDB_URL -or -not $env:AGENTDB_CLIENT_TOKEN) {
    throw "Set COGIT_AGENTDB_URL and AGENTDB_CLIENT_TOKEN from your deployment."
}
$origin = $env:COGIT_AGENTDB_URL.TrimEnd('/')
$headers = @{ Authorization = "Bearer $($env:AGENTDB_CLIENT_TOKEN)" }
Invoke-RestMethod "$origin/v1/data/catalog" -Headers $headers
$headers['Idempotency-Key'] = "reference-create:$RequestId"
$created = Invoke-RestMethod "$origin/v1/data/cogit-finance-requests" `
    -Method Post -Headers $headers -ContentType application/json `
    -Body (@{ requestId = $RequestId; description = "A typed client request." } | ConvertTo-Json)
Invoke-RestMethod "$origin/v1/data/cogit-finance-requests?limit=10" -Headers $headers
Invoke-RestMethod "$origin/v1/data/cogit-finance-requests/$($created.objectId)" -Headers $headers
$headers['Idempotency-Key'] = "reference-close:$RequestId"
Invoke-RestMethod "$origin/v1/data/cogit-finance-requests/$($created.objectId)/actions/close" `
    -Method Post -Headers $headers -ContentType application/json `
    -Body (@{ expectedRevision = $created.revision } | ConvertTo-Json)
