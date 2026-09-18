# fxqual8 を fxqual7 の後ろに繋ぐ（第18報）。
#
# ⚠️ fxqual7 は**別セッション**のラウンド（SCA 建値ストップ）。そちらが
#    EA のデプロイと再コンパイルをやるので、ここでは原則コンパイルしない。
#    ただし「デプロイ済みの .mq5 に `ScaRevOnlyMask` が入っていない」場合だけは
#    このラウンドが成立しないので、その時に限って自分でデプロイ＋コンパイルする。
#    （fxqual7 が中止された場合の保険）
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\fxqual8\chain.log'

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

# 別セッションからの依頼（2026-09-19）。ロックだけでは足りない——
# テスターのプロセスが残っている間に .ex5 を差し替えると、走行中の16runが
# 2つの実装に割れる。metatester64 が居ないことも条件にする。
function TesterBusy {
  return $null -ne (Get-Process -Name 'metatester64' -ErrorAction SilentlyContinue)
}
function Quiet { return (-not (LockBusy)) -and (-not (TesterBusy)) }

Say 'CHAIN_START(fxqual8) fxqual7 の完了を待つ（最大10時間）'
$q7log = Join-Path $repo 'ml\fxqual7\measure.log'
$deadline = (Get-Date).AddHours(10)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q7log) -and (Select-String -Path $q7log -Pattern 'FXQUAL7_END|FXQUAL7_ABORT' -Quiet)) {
    if (Quiet) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 10時間待っても fxqual7 が終わらなかった'; exit 1 }

Start-Sleep -Seconds 20
if (-not (Quiet)) { Say 'CHAIN_ABORT 待機後にロック／テスターが動いていた。EAは触らない'; exit 1 }

# デプロイ済みの EA に、このラウンドが使う入力が入っているかを確認する。
#
# ⚠️ ここを飛ばすと**静かに嘘の実測が残る**。MT5 は設定ファイルに書かれた
#    「EA が持っていない input」を黙って無視するので、8案すべてが対照と完全同値になり、
#    それが「効かなかった」という結論に化ける（第16報で実際に踏んだ形）。
# 条件は3つとも満たす必要がある:
#   (a) デプロイ済み .mq5 に ScaRevOnlyMask がある
#   (b) リポジトリの .mq5 と内容が一致する（fxqual7 開始後に編集していない）
#   (c) .ex5 が .mq5 より新しい（コンパイル済み）
$deployed = Join-Path $experts 'MIX_EA_SIMVERIFY.mq5'
$deployedEx = Join-Path $experts 'MIX_EA_SIMVERIFY.ex5'
$srcMq5 = Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5'
$needDeploy = $true
if ((Test-Path $deployed) -and (Test-Path $deployedEx)) {
  $hasInput = Select-String -Path $deployed -Pattern 'ScaRevOnlyMask' -Quiet
  $sameSrc  = ((Get-FileHash $deployed).Hash -eq (Get-FileHash $srcMq5).Hash)
  $freshEx  = ((Get-Item $deployedEx).LastWriteTime -ge (Get-Item $deployed).LastWriteTime)
  Say ("DEPLOY_CHECK hasInput={0} sameSrc={1} freshEx={2}" -f $hasInput, $sameSrc, $freshEx)
  if ($hasInput -and $sameSrc -and $freshEx) { $needDeploy = $false }
}
if ($needDeploy) {
  Say 'デプロイ済みEAが条件を満たさない。自分でデプロイして再コンパイルする'
  Copy-Item (Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5') $deployed -Force
  $clog = Join-Path $experts 'c_simverify_rev.log'
  & $med "/compile:$deployed" "/log:$clog"
  Start-Sleep -Seconds 3
  $text = ''
  if (Test-Path $clog) { $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog)) }
  $res = ($text -split "`r?`n" | Where-Object { $_ -match '^Result:' } | Select-Object -Last 1)
  Say ("COMPILE {0}" -f $res)
  if ($res -notmatch '0 errors') { Say 'CHAIN_ABORT コンパイルに失敗した。走らせない'; exit 1 }
} else {
  Say 'デプロイ済みEAは条件を満たしている。コンパイルはしない'
}

Say 'FXQUAL8 を開始する（SCAのリバーサル部分集合を入口に移す・7案＋対照・16run）'
Set-Location $repo
& $py 'ml\fxqual8\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
$code = $LASTEXITCODE
Say ("CHAIN_END exit={0}" -f $code)

# 落ちていたら1度だけ起こし直す（measure.py は done を読むので途中から再開する）。
$q8log = Join-Path $repo 'ml\fxqual8\measure.log'
$ok = (Test-Path $q8log) -and (Select-String -Path $q8log -Pattern 'FXQUAL8_END' -Quiet)
if (-not $ok) {
  Say 'FXQUAL8_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual8\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else {
    Say 'CHAIN_RETRY_SKIP ロックが取られていた'
  }
}
