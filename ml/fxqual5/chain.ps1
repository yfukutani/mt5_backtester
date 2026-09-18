# fxqual5 を fxqual4 の後ろに繋ぐ（第17報）。
#
# fxqual4 と同じく **EA は触らない**（`ScaFil*` は第14報で既に入っている入力）。
# したがってコンパイルもデプロイも行わない。待つのは「fxqual4 が終わってロックが空くこと」だけ。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqual5\chain.log'

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

Say 'CHAIN_START(fxqual5) fxqual4 の完了を待つ（最大6時間）'
$q4log = Join-Path $repo 'ml\fxqual4\measure.log'
$deadline = (Get-Date).AddHours(6)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q4log) -and (Select-String -Path $q4log -Pattern 'FXQUAL4_END|FXQUAL4_ABORT' -Quiet)) {
    if (-not (LockBusy)) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 6時間待っても fxqual4 が終わらなかった'; exit 1 }

Start-Sleep -Seconds 20
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた'; exit 1 }

Say 'FXQUAL5 を開始する（SCA 発注時間帯フィルタ4案＋対照・10run）'
Set-Location $repo
& $py 'ml\fxqual5\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
