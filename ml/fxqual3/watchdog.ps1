# ラウンドが死んだら起こし直すウォッチドッグ（第16報・fxqual3 用）。
#
# 【fxqual2 用との違い — ここが重要】
# fxqual2 のウォッチドッグは `measure.py` を直接起こし直していた。
# **fxqual3 で同じことをしてはいけない。** fxqual3 は EA の再コンパイルを伴う
# （`RsiMechMask_*` / `PbDiagCounters` は第16報で足した入力で、旧 .ex5 には無い）。
# 旧 .ex5 のまま measure.py だけ起こすと、**MT5 は知らない入力を黙って無視する**ので
# V001〜V006 が V000 と完全に同じ数字になり、「差が出なかった」という
# **偽の実測**が results.csv に残る。これは最悪の壊れ方である。
# したがって起こし直すのは **chain.ps1** のほうにする。chain.ps1 は
#   - FXQUAL2_END を待つ（もう出ていれば素通り）
#   - 同じソースを再コンパイルする（同じソースなので結果は変わらない）
#   - measure.py を呼ぶ（results.csv にある run は飛ばす）
# のいずれも冪等なので、何度呼んでも安全である。
#
# 【起こす条件】5分おきに見て、次が同時に成り立ったとき:
#   1. measure.log に FXQUAL3_END / FXQUAL3_ABORT が無い
#   2. chain.ps1 の powershell も、fxqual3 の python も、metatester64 も走っていない
#   3. fxqual3 のログが15分以上更新されていない
#
# ⚠️ このファイルは **UTF-8 BOM付き**で保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$mlog = Join-Path $repo 'ml\fxqual3\measure.log'
$clog = Join-Path $repo 'ml\fxqual3\chain.log'
$wlog = Join-Path $repo 'ml\fxqual3\watchdog.log'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$chain = Join-Path $repo 'ml\fxqual3\chain.ps1'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $wlog -Value $line -Encoding utf8
}

Say 'WATCHDOG_START fxqual3 を見張る（5分おき・最大10時間）'
$deadline = (Get-Date).AddHours(10)
$restarts = 0
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 300

  if ((Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUAL3_END|FXQUAL3_ABORT' -Quiet)) {
    Say 'WATCHDOG_END ラウンドが終わったので抜ける'
    exit 0
  }

  # chain.ps1 を回している powershell、fxqual3 の measure.py、テスターのいずれかが
  # 生きていれば何もしない。**`python` の件数で見てはいけない**（equity DD の
  # 常駐コレクタも python なので、常に生きていると誤判定する。第15報で踏んだ）。
  $ch = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*fxqual3*chain.ps1*' })
  $mp = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*fxqual3*measure.py*' })
  $mt = @(Get-Process metatester64 -ErrorAction SilentlyContinue)
  if ($ch.Count -gt 0 -or $mp.Count -gt 0 -or $mt.Count -gt 0) { continue }

  # fxqual2 がまだ走っているなら、fxqual3 が動いていないのは正常である。
  $q2 = Join-Path $repo 'ml\fxqual2\measure.log'
  if ((Test-Path $q2) -and -not (Select-String -Path $q2 -Pattern 'FXQUAL2_END|FXQUAL2_ABORT' -Quiet)) { continue }

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
  Say ("WATCHDOG_RESTART {0}回目 chain.ps1 を起こし直す（コンパイルから冪等にやり直す）" -f $restarts)
  Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$chain `
    -WorkingDirectory $repo -WindowStyle Hidden
}
Say 'WATCHDOG_TIMEOUT 10時間たったので抜ける'
