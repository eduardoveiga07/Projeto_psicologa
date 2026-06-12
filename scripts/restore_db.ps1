param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    throw "Arquivo .env nao encontrado. Execute na raiz do projeto."
}
if (-not (Test-Path $BackupFile)) {
    throw "Backup nao encontrado: $BackupFile"
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

$fileName = Split-Path $BackupFile -Leaf
$containerPath = "/tmp/$fileName"

Write-Host "ATENCAO: a restauracao apaga objetos existentes do banco '$dbName'."
$confirm = Read-Host "Digite RESTAURAR para continuar"
if ($confirm -ne "RESTAURAR") {
    Write-Host "Restauracao cancelada."
    exit 1
}

docker compose cp $BackupFile "db:$containerPath"
docker compose exec -T db pg_restore -U $dbUser -d $dbName --clean --if-exists --no-owner $containerPath
docker compose exec -T db rm -f $containerPath

Write-Host "Backup restaurado: $BackupFile"
