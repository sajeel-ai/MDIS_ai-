[CmdletBinding()]
param(
    [string]$OutputDirectory = ".\backup-output",
    [int]$RetentionCount = 14
)

$ErrorActionPreference = "Stop"

if ($env:DATABASE_URL -match ":5432/" -or $env:DATABASE_URL -match "/cognate_ai(?:\?|$)") {
    throw "Refusing unsafe DATABASE_URL. Backups may only target the disposable 5433 test database in this environment."
}
if (-not $env:DATABASE_URL) {
    throw "DATABASE_URL is required."
}
if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    throw "pg_dump is required."
}
if (-not (Get-Command age -ErrorAction SilentlyContinue)) {
    throw "age is required for encrypted backups."
}
if (-not $env:BACKUP_AGE_RECIPIENT) {
    throw "BACKUP_AGE_RECIPIENT is required; configure it in the deployment secret store."
}

$uri = [Uri]$env:DATABASE_URL.Replace("postgresql+asyncpg://", "postgresql://")
$database = $uri.AbsolutePath.TrimStart("/")
if ($uri.Port -ne 5433 -or $database -ne "cognate_ai_test" -or $uri.UserInfo -ne "test:test") {
    throw "This local script only permits the disposable test database on port 5433."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$plain = Join-Path $OutputDirectory "cognate-ai-$stamp.dump"
$encrypted = "$plain.age"

try {
    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = [Uri]::UnescapeDataString(($uri.UserInfo -split ":", 2)[1])
    & pg_dump --format=custom --file=$plain --no-owner --no-acl `
        --host $uri.Hostname --port $uri.Port --username test $database
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
    & age --encrypt --recipient $env:BACKUP_AGE_RECIPIENT --output $encrypted $plain
    if ($LASTEXITCODE -ne 0) { throw "age encryption failed." }
}
finally {
    $env:PGPASSWORD = $previousPassword
    if (Test-Path $plain) { Remove-Item -Force $plain }
}

Get-ChildItem -Path $OutputDirectory -Filter "*.dump.age" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $RetentionCount |
    Remove-Item -Force

Write-Output "Encrypted backup created: $encrypted"
