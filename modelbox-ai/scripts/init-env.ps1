# Create modelbox-ai/.env from .env.example with freshly generated secrets.
#
# JWT_SECRET, ENCRYPTION_KEY and POSTGRES_PASSWORD each get 32 random bytes as
# 64 hex characters: long enough for the settings check, and URL-safe, since
# the database password is interpolated into a DSN.
#
# Refuses to overwrite an existing .env. Replacing ENCRYPTION_KEY makes every
# stored connection secret unreadable, and replacing POSTGRES_PASSWORD locks
# the appliance out of its own database volume, so there is no -Force.
#
# Prints the names of what it generated, never the values.

#Requires -Version 7
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Example = Join-Path $Root '.env.example'
$Target = Join-Path $Root '.env'
$Generated = @('JWT_SECRET', 'ENCRYPTION_KEY', 'POSTGRES_PASSWORD')

function New-HexSecret {
    $bytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

# guard:begin
if (Test-Path -LiteralPath $Target) {
    Write-Error "$Target already exists; refusing to overwrite it. Its secrets protect existing data. Remove it yourself only if you mean to start over."
    exit 1
}
$Mode = [System.IO.FileMode]::CreateNew
# guard:end

$lines = [System.IO.File]::ReadAllText($Example) -split "`r?`n"
foreach ($name in $Generated) {
    $count = @($lines | Where-Object { $_ -match "^$name=" }).Count
    if ($count -ne 1) {
        Write-Error "$Example must declare $name exactly once; found $count."
        exit 1
    }
}
$out = foreach ($line in $lines) {
    $name = ($line -split '=', 2)[0]
    if ($Generated -contains $name) { "$name=$(New-HexSecret)" } else { $line }
}

# CreateNew fails if the file appeared since the check above.
$stream = [System.IO.File]::Open($Target, $Mode, [System.IO.FileAccess]::Write)
try {
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($out -join "`n"))
    $stream.Write($bytes, 0, $bytes.Length)
} finally {
    $stream.Dispose()
}
Write-Output "Wrote $Target with generated $($Generated -join ', ')."
