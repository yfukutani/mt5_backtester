# 第15報（発火理由の計装）を fxqual1 の後ろに並べる。
#
# 【並び】 fxqual1（走行中・44run）→ EA差し替え＋再コンパイル → fxqual2（2run）
#
# 【EA を差し替える理由】
# 走行中の .ex5 は第14報のもので、`TagDealTriggers` を持っていない。
# **fxqual1 が終わるまで絶対に差し替えてはいけない**（同一ラウンド内で EA が変わる）。
# ここでは FXQUAL1_END を待ってから差し替える。
#
# 【差し替えても fxqual1 の結果は変わらない】
# 追加分はコメント文字列と deals ダンプの1列だけで、売買判断に触れていない。
# それを主張ではなく**実測**にするのが fxqual2 の T000 で、
# fxqual1 の Q000 と1円まで一致しなければならない（analyze.py が最初に出す）。
#
# ⚠️ このファイルは **UTF-8 BOM付き**で保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual2\chain.log'

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

Say 'CHAIN_START(fxqual2) fxqual1 の完了を待つ（最大12時間）'
$q1log = Join-Path $repo 'ml\fxqual1\measure.log'
$deadline = (Get-Date).AddHours(12)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q1log) -and (Select-String -Path $q1log -Pattern 'FXQUAL1_END|FXQUAL1_ABORT' -Quiet)) {
    if (-not (LockBusy)) { break }
  }
  Start-Sleep -Seconds 120
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 12時間待っても fxqual1 が終わらなかった'; exit 1 }

Start-Sleep -Seconds 30
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた。EAは触らない'; exit 1 }

Say '計装入りの EA をデプロイして再コンパイルする'
Copy-Item (Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5') (Join-Path $experts 'MIX_EA_SIMVERIFY.mq5') -Force
$clog = Join-Path $experts 'c_simverify_tag.log'
& $med "/compile:$(Join-Path $experts 'MIX_EA_SIMVERIFY.mq5')" "/log:$clog"
Start-Sleep -Seconds 3
$result = ''
if (Test-Path $clog) {
  $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog))
  $result = ($text -split "`r?`n" | Where-Object { $_ -like 'Result:*' }) -join ' '
}
Say ("COMPILE {0}" -f $result)
if ($result -notlike '*0 errors*') { Say 'CHAIN_ABORT コンパイルにエラー'; exit 1 }

Say 'FXQUAL2 を開始する（計装ON対照+Pair7案 x OOS/IS = 16run）'
Set-Location $repo
& $py 'ml\fxqual2\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
