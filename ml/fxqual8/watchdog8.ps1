# fxqual8 のチェーンが死んだら起こし直す（第18報）。
#
# ⚠️ 別セッションの watchdog は fxqual5/6/7 だけを見る。**fxqual8 は見ない**ので
#    こちらで持つ。二重に起こさないよう、見る対象は fxqual8 だけに限定する。
#
# ⚠️ 自己ヒットの罠（別セッションが実際に踏んだバグ）:
#    生存判定を `*fxqual8*` のような広いパターンにすると、**この監視スクリプト自身の
#    コマンドラインがヒットして「常に生きている」と誤判定**する。
#    だから照合は `fxqual8\chain.ps1` と、対象そのものの名前で行う。
#    （このファイルのパスは `fxqual8\watchdog8.ps1` なので一致しない）
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$log  = Join-Path $repo 'ml\fxqual8\watchdog8.log'
$chain = Join-Path $repo 'ml\fxqual8\chain.ps1'
$m8log = Join-Path $repo 'ml\fxqual8\measure.log'
$self = $PID

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

function ChainAlive {
  $p = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
       Where-Object { $_.ProcessId -ne $self -and $_.CommandLine -like '*fxqual8\chain.ps1*' }
  return $null -ne $p
}
function MeasureAlive {
  $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
       Where-Object { $_.CommandLine -like '*fxqual8\measure.py*' }
  return $null -ne $p
}
function Finished {
  return (Test-Path $m8log) -and (Select-String -Path $m8log -Pattern 'FXQUAL8_END|FXQUAL8_ABORT' -Quiet)
}

Say ("WATCHDOG8_START self={0}" -f $self)
$revives = 0
$deadline = (Get-Date).AddHours(14)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 180
  if (Finished) { Say 'WATCHDOG8_DONE FXQUAL8 が終了している'; break }
  if (ChainAlive -or (MeasureAlive)) { continue }
  if ($revives -ge 3) { Say 'WATCHDOG8_GIVEUP 3回起こしても続かなかった'; break }
  $revives++
  Say ("WATCHDOG8_REVIVE {0}回目 チェーンもmeasureも居ないので起こし直す" -f $revives)
  Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$chain -WindowStyle Hidden
  Start-Sleep -Seconds 30
}
if ((Get-Date) -ge $deadline) { Say 'WATCHDOG8_TIMEOUT 14時間で見張りを終える' }
