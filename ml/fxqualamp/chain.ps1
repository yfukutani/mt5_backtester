# fxqualamp を fxqual10 の後ろに繋ぐ（第17報の追加ラウンド）。
#
# **EA は触らない**（使うのは既存 input だけ）。デプロイもコンパイルもしない。
# 待つのは「fxqual10 が終わってロックが空き、テスターが居ないこと」。
#
# ⚠️ 並行セッションがさらに別のラウンドを積む可能性があるので、
#    ロックが空くまで粘る（最大12時間）。measure.py の acquire_lock() に負けると
#    **何もせずに正常終了する**ので、ウォッチドッグ側で FXQUALAMP_END を見て起こし直す。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqualamp\chain.log'

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

Say 'CHAIN_START(fxqualamp) fxqual10 の完了とロックの解放を待つ（最大12時間）'
$q10 = Join-Path $repo 'ml\fxqual10\measure.log'
$deadline = (Get-Date).AddHours(12)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q10) -and (Select-String -Path $q10 -Pattern 'FXQUAL10_END|FXQUAL10_ABORT' -Quiet)) {
    if (-not (Busy)) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 12時間待っても走れる状態にならなかった'; exit 1 }

Start-Sleep -Seconds 30
$waited = 0
while ((Busy) -and $waited -lt 36000) { Start-Sleep -Seconds 60; $waited += 60 }
if (Busy) { Say 'CHAIN_ABORT ロックがずっと埋まっていた'; exit 1 }

Say 'FXQUALAMP を開始する（複利の増幅の内訳・5案 × 3窓 = 15run・EAは触らない）'
Set-Location $repo
& $py 'ml\fxqualamp\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
