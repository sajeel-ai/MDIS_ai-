[CmdletBinding()]
param(
    [string]$BackupFile = "",
    [string]$StorageKey = ""
)

$ErrorActionPreference = "Stop"

if ($env:DATABASE_URL -match ":5432/" -or $env:DATABASE_URL -match "/cognate_ai(?:\?|$)") {
    throw "Refusing unsafe DATABASE_URL. Restore tests may only target the disposable 5433 test database."
}
if (-not $env:DATABASE_URL) { throw "DATABASE_URL is required." }
if (-not (Get-Command age -ErrorAction SilentlyContinue)) { throw "age is required." }
if (-not (Get-Command pg_restore -ErrorAction SilentlyContinue)) { throw "pg_restore is required." }
if (-not $env:BACKUP_AGE_IDENTITY_FILE) { throw "BACKUP_AGE_IDENTITY_FILE is required." }

$uri = [Uri]$env:DATABASE_URL.Replace("postgresql+asyncpg://", "postgresql://")
if (
    $uri.Port -ne 5433 -or
    $uri.AbsolutePath.TrimStart("/") -ne "cognate_ai_test" -or
    $uri.UserInfo -ne "test:test"
) {
    throw "This local script only permits the disposable test database on port 5433."
}
if (-not $BackupFile) {
    $BackupFile = Get-ChildItem ".\backup-output\*.dump.age" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $BackupFile -or -not (Test-Path $BackupFile)) { throw "Encrypted backup file not found." }

$plain = Join-Path $env:TEMP "cognate-restore-$([Guid]::NewGuid()).dump"
try {
    $previousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = "test"
    & age --decrypt --identity $env:BACKUP_AGE_IDENTITY_FILE --output $plain $BackupFile
    if ($LASTEXITCODE -ne 0) { throw "age decryption failed." }
    & pg_restore --clean --if-exists --no-owner --no-acl `
        --host $uri.Hostname --port $uri.Port --username test --dbname cognate_ai_test $plain
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed." }

    Push-Location backend
    try {
        & ..\.venv-312\Scripts\python.exe -m alembic current
        if ($LASTEXITCODE -ne 0) { throw "Migration version verification failed." }
        & ..\.venv-312\Scripts\python.exe scripts\verify_restore.py -StorageKey $StorageKey
        if ($LASTEXITCODE -ne 0) { throw "Restore verification failed." }
    }
    finally { Pop-Location }
}
finally {
    $env:PGPASSWORD = $previousPassword
    if (Test-Path $plain) { Remove-Item -Force $plain }
}

Write-Output "Restore verification completed against the disposable test database."
