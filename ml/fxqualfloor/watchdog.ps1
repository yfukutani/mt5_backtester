# fxqualfloor のウォッチドッグ（第17報の追加ラウンド）。
#
# 【塞ぎたい穴】
# 他ラウンドと同じ時間帯に走りうるので、`measure.py` の
# `acquire_lock()` が**負けて黙って return する**可能性がある。そのとき
# `chain.ps1` は「CHAIN_END exit=0」を出して正常終了するので、
# **1run も走っていないのに成功に見える。** これが一番危ない壊れ方である。
#
# したがって「終わったか」は **exit code ではなく `measure.log` の
# `FXQUALFLOOR_END`** で判定し、無ければ `chain.ps1` を起こし直す。
# `chain.ps1` も `measure.py` も冪等（済んだ run は results.csv を見て飛ばす）。
#
# ⚠️ 照合は `*fxqualfloor\chain.ps1*` と名指しする。`*fxqualfloor*` だと
#    このウォッチドッグ自身のパスに必ずヒットして永久に「生きている」と誤判定する
#    （第17報で実際に踏んだ）。
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo  = 'C:\Users\f\source\repos\mt5_backtester'
$mlog  = Join-Path $repo 'ml\fxqualfloor\measure.log'
$clog  = Join-Path $repo 'ml\fxqualfloor\chain.log'
$wlog  = Join-Path $repo 'ml\fxqualfloor\watchdog.log'
$chain = Join-Path $repo 'ml\fxqualfloor\chain.ps1'
$lock  = Join-Path $repo 'ml\fxmargin3\measure.lock'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $wlog -Value $line -Encoding utf8
}

function LockBusy {
  if (-not (Test-Path $lock)) { return $false }
  $t = (Get-Content $lock -Raw -ErrorAction SilentlyContinue)
  if ($null -eq $t) { return $false }
  $t = $t.Trim()
  if ($t -notmatch '^\d+$') { return $false }
  return $null -ne (Get-Process -Id ([int]$t) -ErrorAction SilentlyContinue)
}

Say 'WATCHDOG_START fxqualfloor を見張る（5分おき・最大12時間）'
$deadline = (Get-Date).AddHours(12)
$restarts = 0
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 300

  if ((Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUALFLOOR_END|FXQUALFLOOR_ABORT' -Quiet)) {
    Say 'WATCHDOG_END ラウンドが終わったので抜ける'
    exit 0
  }

  # 誰かがテスターを回しているなら待つ（fxqual9 かもしれない）
  if (Get-Process metatester64 -ErrorAction SilentlyContinue) { continue }
  if (LockBusy) { continue }

  # 自分の chain が生きているなら何もしない
  $ch = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*fxqualfloor\chain.ps1*' })
  $mp = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*fxqualfloor*measure.py*' })
  if ($ch.Count -gt 0 -or $mp.Count -gt 0) { continue }

  # fxqual8 がまだなら、動いていないのは正常
  $qprev = Join-Path $repo 'ml\fxqualamp\measure.log'
  if ((Test-Path $qprev) -and -not (Select-String -Path $qprev -Pattern 'FXQUALAMP_END|FXQUALAMP_ABORT' -Quiet)) { continue }

  if ($restarts -ge 8) { Say 'WATCHDOG_ABORT 8回起こしても続かない。手で見ること'; exit 1 }
  $restarts++
  Say ("WATCHDOG_RESTART {0}回目 chain.ps1 を起こし直す（ロックに負けて黙って降りた可能性）" -f $restarts)
  Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$chain `
    -WorkingDirectory $repo -WindowStyle Hidden
}
Say 'WATCHDOG_TIMEOUT 12時間たったので抜ける'
