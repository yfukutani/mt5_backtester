# update_funding.ps1 - daily funding CSV update for FundingRev_EA (fallback mode)
#
# Use ONLY when the EA's built-in WebRequest cannot be used on the ops PC
# (URL not whitelistable / network policy). Normal setup needs no script:
# the EA fetches Binance funding itself (see docs/fundingrev_live_setup.md).
#
# What it does:
#   1. python ml/fetch_btc_alt_data.py --funding-only  -> ml/funding_btc.csv
#   2. copy the CSV to MT5 Common\Files (where the EA reads it)
#
# Register as a daily task (run in an elevated prompt, adjust paths):
#   schtasks /Create /TN "MT5\UpdateFunding" /SC DAILY /ST 06:30 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\repo\ops\update_funding.ps1"
#
# NOTE: keep this file ASCII-only. PowerShell 5.1 reads BOM-less .ps1 as ANSI
# and non-ASCII comments can corrupt parsing.

param(
    [string]$RepoDir   = (Split-Path -Parent $PSScriptRoot),
    [string]$CommonDir = (Join-Path $env:APPDATA "MetaQuotes\Terminal\Common\Files")
)

$ErrorActionPreference = "Stop"
$log = Join-Path $PSScriptRoot "update_funding.log"

function Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $log -Value $line -Encoding ASCII
    Write-Output $line
}

try {
    python (Join-Path $RepoDir "ml\fetch_btc_alt_data.py") --funding-only
    if ($LASTEXITCODE -ne 0) { throw "fetch script exit code $LASTEXITCODE" }

    $src = Join-Path $RepoDir "ml\funding_btc.csv"
    if (-not (Test-Path $src)) { throw "funding_btc.csv not found: $src" }
    if (-not (Test-Path $CommonDir)) { throw "MT5 Common\Files not found: $CommonDir" }

    Copy-Item $src (Join-Path $CommonDir "funding_btc.csv") -Force
    $rows = (Get-Content $src | Measure-Object -Line).Lines - 1
    Log ("OK rows=" + $rows)
    exit 0
} catch {
    Log ("FAIL " + $_.Exception.Message)
    exit 1
}
