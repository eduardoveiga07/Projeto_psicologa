param(
    [string]$OutputDir = "backups"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    throw "Arquivo .env nao encontrado. Execute na raiz do projeto."
}

$envVars = @{}
Get-Content ".env" | ForEach-Object {
    if ($_ -match "^\s*#" -or $_ -notmatch "=") { return }
    $k, $v = $_.Split("=", 2)
    $envVars[$k.Trim()] = $v.Trim()
}

$dbUser = $envVars["POSTGRES_USER"]
$dbName = $envVars["POSTGRES_DB"]
if (-not $dbUser -or -not $dbName) {
    throw "POSTGRES_USER e POSTGRES_DB precisam estar definidos no .env."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$fileName = "${dbName}_${timestamp}.dump"
$containerPath = "/tmp/$fileName"
$localPath = Join-Path $OutputDir $fileName

docker compose exec -T db pg_dump -U $dbUser -d $dbName -F c -f $containerPath
docker compose cp "db:$containerPath" $localPath
docker compose exec -T db rm -f $containerPath

Write-Host "Backup criado em: $localPath"
