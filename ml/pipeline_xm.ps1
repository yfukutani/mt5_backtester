# XM端末で回すラウンドを1本のパイプラインに並べる（2026-09-17）。
#
# 【なぜ1本にまとめたか】
# ラウンドごとに chain を立てると「どれが次か」が分散して、
# 差し込み・並べ替えのたびに複数プロセスを殺して立て直すことになる。
# 2026-09-15 の chain はそれで落ちて2日ぶん機械を遊ばせた。**順序は1箇所に書く。**
#
# 【順序と理由】
#   1. fxwin2    判定の標本を 3本→7本 に増やす。**いまの見出し数字が本物かを決める**ので最優先
#   2. fxbudget1 枠ごとの証拠金予算（Codex #4）。第10報が「顔ぶれを変える案は生きている」と示した
#                ※このラウンドの直前に **EA を差し替えて再コンパイル**する（Bud_* を使うため）
#   3. fxcarry1  Carry をサイズ/複利/保有/退出に分解。上位候補はどれも Carry を止めているので
#                優先度は下がったが、**最悪窓を支える分散源**なので残す
#
# 共有ロック（ml/fxmargin3/measure.lock）が空くまで待ってから次へ進む。
# OANDA端末のラウンド（ml/fxoanda2）は別インストールなので、これと**並行して**走る。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$med     = 'C:\Users\f\AppData\Roaming\XMTrading MT5\MetaEditor64.exe'
$lock    = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log     = Join-Path $repo 'ml\pipeline_xm.log'

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

function WaitLock([int]$hours) {
  $dl = (Get-Date).AddHours($hours)
  while ((Get-Date) -lt $dl) {
    if (-not (LockBusy)) { Start-Sleep -Seconds 20; if (-not (LockBusy)) { return $true } }
    Start-Sleep -Seconds 60
  }
  return $false
}

Say 'PIPELINE_START fxwin2 -> fxbudget1(EA差し替え) -> fxcarry1'

# --- 1. fxwin2 ---------------------------------------------------------------
if (-not (WaitLock 12)) { Say 'PIPELINE_ABORT ロックが12時間空かなかった(1)'; exit 1 }
Say 'FXWIN2 を開始する'
Set-Location $repo
& $py 'ml\fxwin2\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("FXWIN2 終了 exit={0}" -f $LASTEXITCODE)

# --- 2. fxbudget1（ここでだけ EA を差し替える）--------------------------------
if (-not (WaitLock 12)) { Say 'PIPELINE_ABORT ロックが12時間空かなかった(2)'; exit 1 }
Say 'EA をデプロイして再コンパイルする（Bud_* を使うため）'
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
if ($result -notlike '*0 errors*') { Say 'PIPELINE_ABORT コンパイルにエラー'; exit 1 }
Say 'FXBUDGET1 を開始する'
& $py 'ml\fxbudget1\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("FXBUDGET1 終了 exit={0}" -f $LASTEXITCODE)

# --- 3. fxcarry1 -------------------------------------------------------------
if (-not (WaitLock 12)) { Say 'PIPELINE_ABORT ロックが12時間空かなかった(3)'; exit 1 }
Say 'FXCARRY1 を開始する'
& $py 'ml\fxcarry1\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("FXCARRY1 終了 exit={0}" -f $LASTEXITCODE)

Say 'PIPELINE_END'
