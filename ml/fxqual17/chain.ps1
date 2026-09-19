# fxqual17 を fxqual16 の後ろに繋ぐ（第29報）。
#
# ⚠️ このラウンドは **XM 端末に計装入りの EA をデプロイして再コンパイルする**。
#    `TrackMarginLevel()`（`cc86514`・並行セッションが実装）は受動的だが、
#    **載っていなければ維持率は1件も記録されない**ので、DEPLOY_CHECK で必ず確認する。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual17\chain.log'

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
function TesterBusy { return $null -ne (Get-Process -Name 'metatester64' -ErrorAction SilentlyContinue) }
function Quiet { return (-not (LockBusy)) -and (-not (TesterBusy)) }

Say 'CHAIN_START(fxqual17) fxqual16 の完了とロックの解放を待つ（最大8時間）'
$prev = Join-Path $repo 'ml\fxqual16\measure.log'
$deadline = (Get-Date).AddHours(8)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $prev) -and (Select-String -Path $prev -Pattern 'FXQUAL16_END|FXQUAL16_ABORT' -Quiet)) {
    if (Quiet) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 8時間待っても走れる状態にならなかった'; exit 1 }

Start-Sleep -Seconds 30
if (-not (Quiet)) { Say 'CHAIN_ABORT 待機後にロック／テスターが動いていた。EAは触らない'; exit 1 }

$deployed   = Join-Path $experts 'MIX_EA_SIMVERIFY.mq5'
$deployedEx = Join-Path $experts 'MIX_EA_SIMVERIFY.ex5'
$srcMq5     = Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5'

# 計装がリポジトリ側に入っていることを先に確認する。
foreach ($tok in @('TrackMarginLevel','margin_level_min','margin_level_hist','NOT_MEASURED')) {
  if (-not (Select-String -Path $srcMq5 -Pattern $tok -Quiet)) {
    Say ("CHAIN_ABORT リポジトリの .mq5 に {0} が無い。計装が入っていない" -f $tok)
    exit 1
  }
}

Set-Content -Path $lock -Value $PID -Encoding ascii
Say ("LOCK_HELD pid={0} デプロイとコンパイルの間だけ押さえる" -f $PID)

Copy-Item $srcMq5 $deployed -Force
$clog = Join-Path $experts 'c_simverify_marginlevel.log'
$compileArg = '/compile:' + $deployed
$logArg = '/log:' + $clog
& $med $compileArg $logArg
Start-Sleep -Seconds 3
$text = ''
if (Test-Path $clog) { $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog)) }
$res = ($text -split "`r?`n" | Where-Object { $_ -match '^Result:' } | Select-Object -Last 1)
Say ("COMPILE {0}" -f $res)
if ($res -notmatch '0 errors') {
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  Say 'CHAIN_ABORT コンパイルに失敗した。走らせない（ロックは返した）'
  exit 1
}

$hasA  = Select-String -Path $deployed -Pattern 'TrackMarginLevel' -Quiet
$hasB  = Select-String -Path $deployed -Pattern 'NOT_MEASURED' -Quiet
$same  = ((Get-FileHash $deployed).Hash -eq (Get-FileHash $srcMq5).Hash)
$fresh = ((Get-Item $deployedEx).LastWriteTime -ge (Get-Item $deployed).LastWriteTime)
Say ("DEPLOY_CHECK hasTrack={0} hasNotMeasured={1} sameSrc={2} freshEx={3}" -f $hasA,$hasB,$same,$fresh)
if (-not ($hasA -and $hasB -and $same -and $fresh)) {
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  Say 'CHAIN_ABORT デプロイ検査に落ちた（ロックは返した）'
  exit 1
}

Remove-Item $lock -Force -ErrorAction SilentlyContinue
Say 'LOCK_RELEASED measure.py に渡す'

Say 'FXQUAL17 を開始する（倍率1/2/3 x Carry あり/抜き・cap90・12run・全 run が回帰試験）'
Set-Location $repo
& $py 'ml\fxqual17\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)

$mlog = Join-Path $repo 'ml\fxqual17\measure.log'
if (-not ((Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUAL17_END' -Quiet))) {
  Say 'FXQUAL17_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual17\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else { Say 'CHAIN_RETRY_SKIP ロックが取られていた' }
}
