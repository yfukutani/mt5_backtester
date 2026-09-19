# fxqualcfm を fxqual8 の後ろに繋ぐ（第17報の確認ラウンド）。
#
# **EA は触らない**（使うのは既存 input だけ: RsiMechMask_UJ / PbSlopeATR_UJ /
# FxRiskMask / FxRiskPct / FxRiskRefCap / RefCap_* / GlobalLotMult）。
# したがってデプロイもコンパイルも行わない。待つのは
# 「fxqual8 が終わってロックが空き、テスターが居ないこと」だけ。
#
# ⚠️ 並行セッションが ml/fxqual9（PbArmMaxBars / PairRequireZTurning）を
#    同じく fxqual8 の後ろに繋ぐ可能性がある。measure.py のロックで同時実行は防げるが、
#    負けたほうは**何もせずに終了する**（acquire_lock が false で return）ので、
#    こちらは**ロックが空くまで待ち続ける**ようにしてある（最大10時間）。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqualcfm\chain.log'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

function Busy {
  if (Get-Process metatester64 -ErrorAction SilentlyContinue) { return $true }
  if (-not (Test-Path $lock)) { return $false }
  $t = (Get-Content $lock -Raw -ErrorAction SilentlyContinue)
  if ($null -eq $t) { return $false }
  $t = $t.Trim()
  if ($t -notmatch '^\d+$') { return $false }
  return $null -ne (Get-Process -Id ([int]$t) -ErrorAction SilentlyContinue)
}

Say 'CHAIN_START(fxqualcfm) fxqual8 の完了とロックの解放を待つ（最大10時間）'
$q8log = Join-Path $repo 'ml\fxqual8\measure.log'
$deadline = (Get-Date).AddHours(10)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q8log) -and (Select-String -Path $q8log -Pattern 'FXQUAL8_END|FXQUAL8_ABORT' -Quiet)) {
    if (-not (Busy)) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 10時間待っても走れる状態にならなかった'; exit 1 }

# 並行セッションのラウンドが先に取っているかもしれないので、空くまで粘る。
Start-Sleep -Seconds 30
$waited = 0
while ((Busy) -and $waited -lt 36000) { Start-Sleep -Seconds 60; $waited += 60 }
if (Busy) { Say 'CHAIN_ABORT ロックがずっと埋まっていた'; exit 1 }

Say 'FXQUALCFM を開始する（採用候補2件 × 3サイジング × 3窓 = 18run・EAは触らない）'
Set-Location $repo
& $py 'ml\fxqualcfm\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
