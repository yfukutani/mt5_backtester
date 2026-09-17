# fxcarry1（第11報）の終了を待って、枠ごとの証拠金予算ラウンド（第13報）を始める。
#
# 【EA を差し替えるのはここだけ】
# 本ラウンドは `Bud_*`（枠ごとの証拠金予算・既定0で従来と同一挙動）を使うので、
# EA の再デプロイと再コンパイルが要る。走行中に .ex5 を差し替えると measure.py が
# 「EAバイナリが測定中に入れ替わった」で落ちるので、**必ず待ってから**触る。
#
# 待つ条件は2つとも満たすこと:
#   ① ml/fxcarry1/measure.log に FXCARRY1_END か FXCARRY1_ABORT がある
#   ② 共有ロック ml/fxmargin3/measure.lock が空いている（端末は1台しか使えない）
#
# 既定 `Bud_*=0` は従来と1ビットも変わらないはずなので、対照 B000 が
# fxvmax1 の O003 を1円まで再現することを measure.py 側で確認する（再現しなければ止まる）。
$ErrorActionPreference = 'Continue'
$repo     = 'C:\Users\f\source\repos\mt5_backtester'
$py       = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts  = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med      = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock     = Join-Path $repo 'ml\fxmargin3\measure.lock'
$carryLog = Join-Path $repo 'ml\fxcarry1\measure.log'
$log      = Join-Path $repo 'ml\fxbudget1\chain.log'

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

Say 'CHAIN_START(ps1) fxcarry1 の完了と共有ロックの解放を待つ（最大20時間）'
$deadline = (Get-Date).AddHours(20)
while ((Get-Date) -lt $deadline) {
  $carryDone = $false
  if (Test-Path $carryLog) {
    if (Select-String -Path $carryLog -Pattern 'FXCARRY1_END|FXCARRY1_ABORT' -Quiet) { $carryDone = $true }
  }
  if ($carryDone -and -not (LockBusy)) { break }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 20時間待っても条件が揃わなかった'; exit 1 }

Start-Sleep -Seconds 30
if (LockBusy) { Say 'CHAIN_ABORT 待機後にロックが再取得されていた。EAは触らない'; exit 1 }

Say 'EA をデプロイして再コンパイルする'
Copy-Item (Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5') (Join-Path $experts 'MIX_EA_SIMVERIFY.mq5') -Force
$clog = Join-Path $experts 'c_simverify_bud.log'
& $med "/compile:$(Join-Path $experts 'MIX_EA_SIMVERIFY.mq5')" "/log:$clog"
Start-Sleep -Seconds 3
$result = ''
if (Test-Path $clog) {
  $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog))
  $result = ($text -split "`r?`n" | Where-Object { $_ -like 'Result:*' }) -join ' '
}
Say ("COMPILE {0}" -f $result)
if ($result -notlike '*0 errors*') { Say 'CHAIN_ABORT コンパイルにエラー'; exit 1 }

Say 'FXBUDGET1 を開始する'
Set-Location $repo
& $py 'ml\fxbudget1\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
