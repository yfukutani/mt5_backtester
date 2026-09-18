# 第16報（RSI機構ゲート＋PB律速計装）を fxqual2 の後ろに並べる。
#
# 【並び】 fxqual2（走行中・16run）→ EA差し替え＋再コンパイル → fxqual3（14run）
#
# 【EA を差し替える理由】
# 走行中の .ex5 は第15報のもので、`RsiMechMask_*` も `PbDiagCounters` も持っていない。
# **fxqual2 が終わるまで絶対に差し替えてはいけない**（同一ラウンド内で EA が変わる）。
# ここでは FXQUAL2_END を待ってから差し替える。
#
# 【差し替えても fxqual2 の結果は変わらないことを実測で示す】
# 追加分は既定 0/false で挙動に触れない**はず**だが、それを主張で済ませない。
# fxqual3 の V000 が fxqual2 の T000（＝fxqual1 の Q000）と
# 純益・DD・取引数で1円まで一致しなければならない。
#
# ⚠️ このファイルは **UTF-8 BOM付き**で保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual3\chain.log'

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

Say 'CHAIN_START(fxqual3) fxqual2 の完了を待つ（最大12時間）'
$q2log = Join-Path $repo 'ml\fxqual2\measure.log'
$deadline = (Get-Date).AddHours(12)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q2log) -and (Select-String -Path $q2log -Pattern 'FXQUAL2_END|FXQUAL2_ABORT' -Quiet)) {
    if (-not (LockBusy)) { break }
  }
  Start-Sleep -Seconds 120
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 12時間待っても fxqual2 が終わらなかった'; exit 1 }

Start-Sleep -Seconds 30
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた。EAは触らない'; exit 1 }

Say '機構ゲート入りの EA をデプロイして再コンパイルする'
Copy-Item (Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5') (Join-Path $experts 'MIX_EA_SIMVERIFY.mq5') -Force
$clog = Join-Path $experts 'c_simverify_mech.log'
& $med "/compile:$(Join-Path $experts 'MIX_EA_SIMVERIFY.mq5')" "/log:$clog"
Start-Sleep -Seconds 3
$result = ''
if (Test-Path $clog) {
  $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog))
  $result = ($text -split "`r?`n" | Where-Object { $_ -like 'Result:*' }) -join ' '
}
Say ("COMPILE {0}" -f $result)
if ($result -notlike '*0 errors*') { Say 'CHAIN_ABORT コンパイルにエラー'; exit 1 }

Say 'FXQUAL3 を開始する（対照+RSI機構ゲート6案 x OOS/IS = 14run）'
Set-Location $repo
& $py 'ml\fxqual3\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
