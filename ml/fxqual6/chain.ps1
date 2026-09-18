# fxqual6 を fxqual5 の後ろに繋ぐ（第17報）。EA は触らない（既存 input のみ）。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqual6\chain.log'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

function LockBusy {
  if (-not (Test-Path $lock)) { return $false }
  $t = (Get-Content $lock -Raw -ErrorAction SilentlyContinue)
  if ($null -eq $t) { return $false }
  $t = $t.Trim()
  if ($t -notmatch '^\d+$') { return $false }
  return $null -ne (Get-Process -Id ([int]$t) -ErrorAction SilentlyContinue)
}

Say 'CHAIN_START(fxqual6) fxqual5 の完了を待つ（最大6時間）'
$q5log = Join-Path $repo 'ml\fxqual5\measure.log'
$deadline = (Get-Date).AddHours(6)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q5log) -and (Select-String -Path $q5log -Pattern 'FXQUAL5_END|FXQUAL5_ABORT' -Quiet)) {
    if (-not (LockBusy)) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 6時間待っても fxqual5 が終わらなかった'; exit 1 }

Start-Sleep -Seconds 20
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた'; exit 1 }

Say 'FXQUAL6 を開始する（W001 の頑健性・slope の細刻み7案＋対照・16run）'
Set-Location $repo
& $py 'ml\fxqual6\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
