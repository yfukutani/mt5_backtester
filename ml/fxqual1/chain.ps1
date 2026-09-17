# 第14報（枠の質）を、XM端末のパイプラインの後ろに並べる。
#
# 【並び】
#   fxvmax1（走行中・業者上限）
#   → ml\pipeline_xm.ps1（fxwin2 -> fxbudget1 -> fxcarry1）
#   → **fxqual1（本ラウンド）**
#
# 2026-09-17 に、ラウンドごとの chain.ps1 は `ml\pipeline_xm.ps1` に集約された
# （「順序は1箇所に書く」）。既に走っているパイプラインには後から差し込めないので、
# ここでは **PIPELINE_END を待って自分を足す**という形にする。
# 次に順序を組み替えるときは pipeline_xm.ps1 側に fxqual1 を書くこと。
#
# 【EA の扱い】
# 第14報の入力（RsiNoFlip* / ScaHour* / Pb*Ov）は **すべて既定で無効**であり、
# experts\MIX_EA_SIMVERIFY.mq5 の時点で 0 errors/0 warnings を確認済み。
# パイプラインが fxbudget1 の前に同じファイルをコンパイルするので、
# **fxbudget1 の対照が fxvmax1 を1円まで再現すること自体が、
# 第14報の EA 変更が既定挙動を壊していないことの回帰試験になる。**
# ここでも念のため再デプロイ＋再コンパイルしてから走る（パイプラインが中止された場合に備える）。
#
# ⚠️ このファイルは **UTF-8 BOM付き**で保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する（2026-09-18 に踏んだ）。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual1\chain.log'

# 先行の終了マーカー。どちらも「終わった or 中止された」なら進む。
$waitFor = @(
  @{ Name = 'fxvmax1';  Log = (Join-Path $repo 'ml\fxvmax1\measure.log'); Pat = 'FXVMAX1_END|FXVMAX1_ABORT' },
  @{ Name = 'pipeline'; Log = (Join-Path $repo 'ml\pipeline_xm.log');     Pat = 'PIPELINE_END|PIPELINE_ABORT' }
)

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

Say 'CHAIN_START(ps1) fxvmax1 と pipeline_xm の完了、共有ロックの解放を待つ（最大30時間）'
$deadline = (Get-Date).AddHours(30)
while ((Get-Date) -lt $deadline) {
  $allDone = $true
  foreach ($w in $waitFor) {
    $done = $false
    if (Test-Path $w.Log) {
      if (Select-String -Path $w.Log -Pattern $w.Pat -Quiet) { $done = $true }
    }
    if (-not $done) { $allDone = $false; break }
  }
  if ($allDone -and -not (LockBusy)) { break }
  Start-Sleep -Seconds 120
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 30時間待っても条件が揃わなかった'; exit 1 }

Start-Sleep -Seconds 30
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた。EAは触らない'; exit 1 }

Say 'EA をデプロイして再コンパイルする'
Copy-Item (Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5') (Join-Path $experts 'MIX_EA_SIMVERIFY.mq5') -Force
$clog = Join-Path $experts 'c_simverify_qual.log'
& $med "/compile:$(Join-Path $experts 'MIX_EA_SIMVERIFY.mq5')" "/log:$clog"
Start-Sleep -Seconds 3
$result = ''
if (Test-Path $clog) {
  $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog))
  $result = ($text -split "`r?`n" | Where-Object { $_ -like 'Result:*' }) -join ' '
}
Say ("COMPILE {0}" -f $result)
if ($result -notlike '*0 errors*') { Say 'CHAIN_ABORT コンパイルにエラー'; exit 1 }

Say 'FXQUAL1 を開始する（19案 x OOS/IS = 38run）'
Set-Location $repo
& $py 'ml\fxqual1\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
