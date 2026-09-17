# fxvmax1（第12報）の終了を待って fxcarry1（第11報）を始める。
#
# 【なぜ bash の chain.sh ではなく PowerShell なのか】
# 2026-09-15 の chain は、セッション終了と同時に bash ごと落ちて 2日ぶん機械を遊ばせた
# （fxcarry1 も fxvmax1 も 1run も回っていなかった）。`Start-Process -WindowStyle Hidden` で
# 起動した PowerShell はセッションから切り離されるので、同じ落ち方をしない。
#
# 待つ対象は **fxmargin3/measure.lock**（全ラウンド共有。端末は1台しか使えない）。
# EA は触らない——fxcarry1 が使う CarryExitPeriod / CarryHoldBars は
# 既にデプロイ済みの EA に入っており、既定 0 で現行と同一挙動である。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxcarry1\chain.log'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

Say 'CHAIN_START(ps1) 共有ロックが空くのを待つ（最大12時間）'
$deadline = (Get-Date).AddHours(12)
while ((Get-Date) -lt $deadline) {
  $busy = $false
  if (Test-Path $lock) {
    $pidText = (Get-Content $lock -Raw).Trim()
    if ($pidText -match '^\d+$') {
      if (Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue) { $busy = $true }
    }
  }
  if (-not $busy) { break }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 12時間待ってもロックが空かなかった'; exit 1 }

Start-Sleep -Seconds 30
Say 'FXCARRY1 を開始する'
Set-Location $repo
& $py 'ml\fxcarry1\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
