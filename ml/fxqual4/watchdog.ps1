# ラウンドが死んだら起こし直すウォッチドッグ（第17報・fxqual4 用）。
#
# fxqual3 用との違い: **fxqual4 はコンパイルを伴わない**（新 input を使わないため）。
# よって起こし直すのは run.ps1 でよい。measure.py は results.csv にある run を
# 飛ばすので何度呼んでも冪等である。
#
# 【起こす条件】5分おきに見て、次が同時に成り立ったとき:
#   1. measure.log に FXQUAL4_END / FXQUAL4_ABORT が無い
#   2. run.ps1 の powershell も、fxqual4 の python も、metatester64 も走っていない
#   3. fxqual4 のログが15分以上更新されていない
#
# ⚠️ `python` の件数で見てはいけない（別用途の常駐 python があると誤判定する。第15報）。
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$mlog = Join-Path $repo 'ml\fxqual4\measure.log'
$clog = Join-Path $repo 'ml\fxqual4\chain.log'
$wlog = Join-Path $repo 'ml\fxqual4\watchdog.log'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$run  = Join-Path $repo 'ml\fxqual4\run.ps1'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $wlog -Value $line -Encoding utf8
}

Say 'WATCHDOG_START fxqual4 を見張る（5分おき・最大6時間）'
$deadline = (Get-Date).AddHours(6)
$restarts = 0
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 300

  if ((Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUAL4_END|FXQUAL4_ABORT' -Quiet)) {
    Say 'WATCHDOG_END ラウンドが終わったので抜ける'
    exit 0
  }

  $ch = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*fxqual4*run.ps1*' })
  $mp = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*fxqual4*measure.py*' })
  $mt = @(Get-Process metatester64 -ErrorAction SilentlyContinue)
  if ($ch.Count -gt 0 -or $mp.Count -gt 0 -or $mt.Count -gt 0) { continue }

  $newest = $null
  foreach ($f in @($mlog, $clog)) {
    if (Test-Path $f) {
      $t = (Get-Item $f).LastWriteTime
      if ($null -eq $newest -or $t -gt $newest) { $newest = $t }
    }
  }
  if ($null -ne $newest -and ((Get-Date) - $newest).TotalMinutes -lt 15) { continue }

  if ($restarts -ge 5) { Say 'WATCHDOG_ABORT 5回起こし直しても続かない。手で見ること'; exit 1 }
  $restarts++
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  Say ("WATCHDOG_RESTART {0}回目 run.ps1 を起こし直す" -f $restarts)
  Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$run `
    -WorkingDirectory $repo -WindowStyle Hidden
}
Say 'WATCHDOG_TIMEOUT 6時間たったので抜ける'
