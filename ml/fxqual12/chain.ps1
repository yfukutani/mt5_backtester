# fxqual12 を fxqualexec の後ろに繋ぐ（第23報）。
#
# ⚠️ このラウンドは EA を書き換える（ScaRR_UJ/_GJ・ScaOvsATR_UJ/_GJ）ので、
#    自分でデプロイして再コンパイルする。**fxqualexec が完全に終わってからでないと、
#    走行中の run が2つのバイナリに割れる。**
#    したがって FXQUALEXEC_END に加えて、ロックと metatester64 の不在も条件にする。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual12\chain.log'

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

Say 'CHAIN_START(fxqual12) fxqualexec の完了を待つ（最大10時間）'
$prev = Join-Path $repo 'ml\fxqualexec\measure.log'
$deadline = (Get-Date).AddHours(10)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $prev) -and (Select-String -Path $prev -Pattern 'FXQUALEXEC_END|FXQUALEXEC_ABORT' -Quiet)) {
    if (Quiet) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 10時間待っても fxqualexec が終わらなかった'; exit 1 }

Start-Sleep -Seconds 20
if (-not (Quiet)) { Say 'CHAIN_ABORT 待機後にロック／テスターが動いていた。EAは触らない'; exit 1 }

# ⚠️ ここを飛ばすと静かに嘘の実測が残る。MT5 は EA が持っていない input を
#    黙って無視するので、12案すべてが対照と完全同値になり、
#    それが「効かなかった」という結論に化ける（第16報で実際に踏んだ形）。
$deployed   = Join-Path $experts 'MIX_EA_SIMVERIFY.mq5'
$deployedEx = Join-Path $experts 'MIX_EA_SIMVERIFY.ex5'
$srcMq5     = Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5'

foreach ($tok in @('ScaRR_GJ','ScaRR_UJ','ScaOvsATR_GJ','ScaOvsATR_UJ','ScaRROver','ScaOvsOK')) {
  if (-not (Select-String -Path $srcMq5 -Pattern $tok -Quiet)) {
    Say ("CHAIN_ABORT リポジトリの .mq5 に {0} が無い。パッチが当たっていない" -f $tok)
    exit 1
  }
}

# デプロイとコンパイルの間だけ、測定ロックを自分の PID で押さえる。
Set-Content -Path $lock -Value $PID -Encoding ascii
Say ("LOCK_HELD pid={0} デプロイとコンパイルの間だけ押さえる" -f $PID)

Copy-Item $srcMq5 $deployed -Force
$clog = Join-Path $experts 'c_simverify_scarr.log'
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

$hasA  = Select-String -Path $deployed -Pattern 'ScaRR_GJ' -Quiet
$hasB  = Select-String -Path $deployed -Pattern 'ScaOvsATR_GJ' -Quiet
$same  = ((Get-FileHash $deployed).Hash -eq (Get-FileHash $srcMq5).Hash)
$fresh = ((Get-Item $deployedEx).LastWriteTime -ge (Get-Item $deployed).LastWriteTime)
Say ("DEPLOY_CHECK hasRR={0} hasOvs={1} sameSrc={2} freshEx={3}" -f $hasA, $hasB, $same, $fresh)
if (-not ($hasA -and $hasB -and $same -and $fresh)) {
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  Say 'CHAIN_ABORT デプロイ検査に落ちた（ロックは返した）'
  exit 1
}

Remove-Item $lock -Force -ErrorAction SilentlyContinue
Say 'LOCK_RELEASED measure.py に渡す'

Say 'FXQUAL12 を開始する（回帰1＋SCA GJ 重み4＋TP 4＋overshoot 4・26run）'
Set-Location $repo
& $py 'ml\fxqual12\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
$code = $LASTEXITCODE
Say ("CHAIN_END exit={0}" -f $code)

$q12log = Join-Path $repo 'ml\fxqual12\measure.log'
$ok = (Test-Path $q12log) -and (Select-String -Path $q12log -Pattern 'FXQUAL12_END' -Quiet)
if (-not $ok) {
  Say 'FXQUAL12_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual12\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else {
    Say 'CHAIN_RETRY_SKIP ロックが取られていた'
  }
}
