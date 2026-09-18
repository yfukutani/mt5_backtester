# ラウンドが死んだら起こし直すウォッチドッグ（第15報）。
#
# 【なぜ要るか】
# 2026-09-18 01:06 JST に fxvmax1 / pipeline_xm / fxqual2 のチェーンが**全部**落ちた。
# 誰も見ていなかったので **5時間半、1本も走らないまま空転した。**
# 原因は特定できていない（ログは途中で切れており、終了マーカーも異常も残っていない）。
# 原因が分からない以上、**落ちても勝手に起き上がる**ようにしておくのが安い。
#
# 【やること】
# 5分おきに見て、次の3つが同時に成り立ったら measure.py を起こし直す:
#   1. measure.log に FXQUAL1_END / FXQUAL1_ABORT が無い（まだ終わっていない）
#   2. python も metatester64 も走っていない（死んでいる）
#   3. measure.log が15分以上更新されていない（固まっているだけでもない）
# measure.py は results.csv を見て済んだ分を飛ばすので、**再開は安全**である。
#
# 【止めるとき】
# ラウンドが終われば自分で抜ける。手で止めるならプロセスを落とす。
#
# ⚠️ このファイルは **UTF-8 BOM付き**で保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$mlog = Join-Path $repo 'ml\fxqual2\measure.log'
$wlog = Join-Path $repo 'ml\fxqual2\watchdog.log'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $wlog -Value $line -Encoding utf8
}

Say 'WATCHDOG_START fxqual2 を見張る（5分おき・最大8時間）'
$deadline = (Get-Date).AddHours(8)
$restarts = 0
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 300

  if ((Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUAL2_END|FXQUAL2_ABORT' -Quiet)) {
    Say 'WATCHDOG_END ラウンドが終わったので抜ける'
    exit 0
  }

  # **`python` の件数で見てはいけない。** equity DD の常駐コレクタも python なので
  # 常に「生きている」と誤判定し、ウォッチドッグが一度も働かない
  # （2026-09-18 に書いた直後に気づいた）。
  # measure.py を走らせている python だけを、コマンドラインで特定する。
  $mp = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -like '*fxqual2*measure.py*' })
  $mt = @(Get-Process metatester64 -ErrorAction SilentlyContinue)
  if ($mp.Count -gt 0 -or $mt.Count -gt 0) { continue }

  $stale = $true
  if (Test-Path $mlog) {
    $age = (Get-Date) - (Get-Item $mlog).LastWriteTime
    if ($age.TotalMinutes -lt 15) { $stale = $false }
  }
  if (-not $stale) { continue }

  if ($restarts -ge 5) { Say 'WATCHDOG_ABORT 5回起こし直しても続かない。手で見ること'; exit 1 }
  $restarts++
  # 死んだプロセスが置き去りにしたロックを外す（PIDが生きていないことは上で確認済み）。
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  Say ("WATCHDOG_RESTART {0}回目 measure.py を起こし直す（済んだrunは飛ばされる）" -f $restarts)
  Start-Process -FilePath $py -ArgumentList 'ml\fxqual2\measure.py' -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $repo 'ml\fxqual2\stdout.log') `
    -RedirectStandardError  (Join-Path $repo 'ml\fxqual2\stderr.log')
}
Say 'WATCHDOG_TIMEOUT 8時間たったので抜ける'
