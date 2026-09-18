# fxqual7 を fxqual6 の後ろに繋ぐ（第17報）。
#
# ⚠️ **このラウンドは EA を差し替えて再コンパイルする**（`ScaBETriggerR` / `ScaBELockR` /
# `ScaBEMask` は第17報で足した入力で、いま端末にある .ex5 には無い）。
# fxqual4〜fxqual6 は既存 input だけなので EA を触っていない。
# **走行中に差し替えると、残りの run が別のバイナリで走る**ので、
# fxqual6 の完了とロックの解放を確認してから差し替える。
#
# MT5 は知らない input を黙って無視するので、差し替えに失敗したまま measure.py を回すと
# 「7案すべてが対照と完全同値」という**偽の実測**が残る。だから
# コンパイル結果を検査し、`0 errors` でなければ中止する。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual7\chain.log'

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

Say 'CHAIN_START(fxqual7) fxqual6 の完了を待つ（最大8時間）'
$q6log = Join-Path $repo 'ml\fxqual6\measure.log'
$deadline = (Get-Date).AddHours(8)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q6log) -and (Select-String -Path $q6log -Pattern 'FXQUAL6_END|FXQUAL6_ABORT' -Quiet)) {
    if (-not (LockBusy)) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 8時間待っても fxqual6 が終わらなかった'; exit 1 }

Start-Sleep -Seconds 30
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた。EAは触らない'; exit 1 }
if (Get-Process metatester64 -ErrorAction SilentlyContinue) {
  Say 'CHAIN_ABORT テスターがまだ生きている。EAは触らない'; exit 1
}

Say '建値ストップ入りの EA をデプロイして再コンパイルする'
Copy-Item (Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5') (Join-Path $experts 'MIX_EA_SIMVERIFY.mq5') -Force
$clog = Join-Path $experts 'c_simverify_scabe.log'
& $med "/compile:$(Join-Path $experts 'MIX_EA_SIMVERIFY.mq5')" "/log:$clog"
Start-Sleep -Seconds 5
$result = ''
if (Test-Path $clog) {
  $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog))
  $result = ($text -split "`r?`n" | Where-Object { $_ -like 'Result:*' }) -join ' '
}
Say ("COMPILE {0}" -f $result)
if ($result -notlike '*0 errors*') { Say 'CHAIN_ABORT コンパイルにエラー'; exit 1 }

Say 'FXQUAL7 を開始する（SCA 建値ストップ7案＋対照・16run）'
Set-Location $repo
& $py 'ml\fxqual7\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
