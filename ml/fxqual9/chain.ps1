# fxqual9 を fxqual8 の後ろに繋ぐ（第19報）。
#
# ⚠️ このラウンドは EA を書き換える（PbArmMaxBars_UJ/_GJ・PairRequireZTurning）ので、
#    自分でデプロイして再コンパイルする。**fxqual8 が完全に終わってからでないと、
#    走行中の16runが2つのバイナリに割れる。**
#    したがって FXQUAL8_END に加えて、ロックと metatester64 の不在も条件にする。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual9\chain.log'

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

function TesterBusy {
  return $null -ne (Get-Process -Name 'metatester64' -ErrorAction SilentlyContinue)
}
function Quiet { return (-not (LockBusy)) -and (-not (TesterBusy)) }

# ⚠️ 待ち先を fxqual8 から fxqualcfm へ変更した（2026-09-19 09:50・並行セッションの依頼）。
#    fxqual8 完走直後の空きを向こうの fxqualcfm（24run）が先に取ったため。
#    FXQUAL8_END は既に出ているので、そのままだと**向こうの run の合間**に
#    起き出して /compile を打ってしまう（向こうの retry 経路でロックが一瞬空く）。
Say 'CHAIN_START(fxqual9) fxqualcfm の完了を待つ（最大10時間）'
$cfmlog = Join-Path $repo 'ml\fxqualcfm\measure.log'
$deadline = (Get-Date).AddHours(10)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $cfmlog) -and (Select-String -Path $cfmlog -Pattern 'FXQUALCFM_END|FXQUALCFM_ABORT' -Quiet)) {
    if (Quiet) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 10時間待っても fxqualcfm が終わらなかった'; exit 1 }

Start-Sleep -Seconds 20
if (-not (Quiet)) { Say 'CHAIN_ABORT 待機後にロック／テスターが動いていた。EAは触らない'; exit 1 }

# このラウンドは EA を変更しているので、**必ず**デプロイして再コンパイルする。
#
# ⚠️ ここを飛ばすと静かに嘘の実測が残る。MT5 は EA が持っていない input を
#    黙って無視するので、8案すべてが対照と完全同値になり、
#    それが「効かなかった」という結論に化ける（第16報で実際に踏んだ形）。
$deployed   = Join-Path $experts 'MIX_EA_SIMVERIFY.mq5'
$deployedEx = Join-Path $experts 'MIX_EA_SIMVERIFY.ex5'
$srcMq5     = Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5'

if (-not (Select-String -Path $srcMq5 -Pattern 'PbArmMaxBars_UJ' -Quiet)) {
  Say 'CHAIN_ABORT リポジトリの .mq5 に PbArmMaxBars_UJ が無い。パッチが当たっていない'
  exit 1
}
if (-not (Select-String -Path $srcMq5 -Pattern 'PairRequireZTurning' -Quiet)) {
  Say 'CHAIN_ABORT リポジトリの .mq5 に PairRequireZTurning が無い。パッチが当たっていない'
  exit 1
}

# ⚠️ デプロイとコンパイルの間だけ、測定ロックを自分の PID で押さえる（並行セッションの依頼）。
#    向こうの chain（ml/fxqualcfm）も FXQUAL8_END 待ちに入っているので、この隙に
#    向こうの measure.py が起動すると、**走行中のテスターの下で .ex5 が差し替わる。**
#    measure.py は自分で acquire_lock() し直すので、呼ぶ直前に必ず外す。
Set-Content -Path $lock -Value $PID -Encoding ascii
Say ("LOCK_HELD pid={0} デプロイとコンパイルの間だけ押さえる" -f $PID)

Copy-Item $srcMq5 $deployed -Force
$clog = Join-Path $experts 'c_simverify_arm.log'
& $med "/compile:$deployed" "/log:$clog"
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

# コンパイル後の3点確認（fxqual8 と同じ作法）。
$hasA = Select-String -Path $deployed -Pattern 'PbArmMaxBars_UJ' -Quiet
$hasB = Select-String -Path $deployed -Pattern 'PairRequireZTurning' -Quiet
$same = ((Get-FileHash $deployed).Hash -eq (Get-FileHash $srcMq5).Hash)
$fresh = ((Get-Item $deployedEx).LastWriteTime -ge (Get-Item $deployed).LastWriteTime)
Say ("DEPLOY_CHECK hasArm={0} hasZTurn={1} sameSrc={2} freshEx={3}" -f $hasA, $hasB, $same, $fresh)
if (-not ($hasA -and $hasB -and $same -and $fresh)) {
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  Say 'CHAIN_ABORT デプロイ検査に落ちた（ロックは返した）'
  exit 1
}

Remove-Item $lock -Force -ErrorAction SilentlyContinue
Say 'LOCK_RELEASED measure.py に渡す'

Say 'FXQUAL9 を開始する（PB armed の寿命6案＋Pair Z転換1案＋対照・16run）'
Set-Location $repo
& $py 'ml\fxqual9\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
$code = $LASTEXITCODE
Say ("CHAIN_END exit={0}" -f $code)

# 落ちていたら1度だけ起こし直す（measure.py は done を読むので途中から再開する）。
$q9log = Join-Path $repo 'ml\fxqual9\measure.log'
$ok = (Test-Path $q9log) -and (Select-String -Path $q9log -Pattern 'FXQUAL9_END' -Quiet)
if (-not $ok) {
  Say 'FXQUAL9_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual9\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else {
    Say 'CHAIN_RETRY_SKIP ロックが取られていた'
  }
}
