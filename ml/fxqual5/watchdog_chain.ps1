# fxqual5 → fxqual6 → fxqual7 のチェーン全体を見張るウォッチドッグ（第17報）。
#
# 各ラウンドの chain.ps1 / run.ps1 は冪等（measure.py は results.csv にある run を飛ばす）
# なので、死んでいたら該当ラウンドのスクリプトを起こし直せばよい。
#
# 【起こす条件】5分おきに見て、次が同時に成り立ったとき:
#   1. そのラウンドの measure.log に *_END / *_ABORT が無い
#   2. そのラウンドの ps1 も python も、metatester64 も走っていない
#   3. そのラウンドのログが20分以上更新されていない（未着手なら前のラウンドが終わっている）
#
# ⚠️ `python` の件数で見てはいけない（別用途の常駐 python があると誤判定する。第15報）。
# ⚠️ fxqual7 は EA の差し替えとコンパイルを伴うので、**chain.ps1 のほうを**起こす
#    （measure.py だけ起こすと旧 .ex5 のまま走り、偽の実測が残る。第16報の教訓）。
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$wlog = Join-Path $repo 'ml\fxqual5\watchdog_chain.log'

$rounds = @(
  @{ n='fxqual5'; tag='FXQUAL5'; ps=(Join-Path $repo 'ml\fxqual5\measure.py'); starter=(Join-Path $repo 'ml\fxqual5\chain.ps1'); prev=$null },
  @{ n='fxqual6'; tag='FXQUAL6'; ps=(Join-Path $repo 'ml\fxqual6\measure.py'); starter=(Join-Path $repo 'ml\fxqual6\chain.ps1'); prev='FXQUAL5' },
  @{ n='fxqual7'; tag='FXQUAL7'; ps=(Join-Path $repo 'ml\fxqual7\measure.py'); starter=(Join-Path $repo 'ml\fxqual7\chain.ps1'); prev='FXQUAL6' }
)

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $wlog -Value $line -Encoding utf8
}

function Ended([string]$name,[string]$tag) {
  $f = Join-Path $repo ("ml\{0}\measure.log" -f $name)
  if (-not (Test-Path $f)) { return $false }
  return [bool](Select-String -Path $f -Pattern ("{0}_END|{0}_ABORT" -f $tag) -Quiet)
}

Say 'WATCHDOG_START fxqual5/6/7 のチェーンを見張る（5分おき・最大8時間）'
$deadline = (Get-Date).AddHours(8)
$restarts = @{}
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 300

  # 全部終わっていれば抜ける
  $allDone = $true
  foreach ($r in $rounds) { if (-not (Ended $r.n $r.tag)) { $allDone = $false } }
  if ($allDone) { Say 'WATCHDOG_END 3ラウンドとも終わったので抜ける'; exit 0 }

  # テスターが生きているならどれかが走っている
  if (Get-Process metatester64 -ErrorAction SilentlyContinue) { continue }

  foreach ($r in $rounds) {
    if (Ended $r.n $r.tag) { continue }
    # 前のラウンドがまだ終わっていないなら、このラウンドが動いていないのは正常
    if ($null -ne $r.prev) {
      $pn = ($rounds | Where-Object { $_.tag -eq $r.prev }).n
      if (-not (Ended $pn $r.prev)) { break }
    }
    # ⚠️ `*fxqual5*` で照合してはいけない——**このウォッチドッグ自身のパスが
    #    `ml\fxqual5\watchdog_chain.ps1` なので必ず自分にヒットし、fxqual5 は
    #    永久に「生きている」と誤判定される。** chain.ps1 / run.ps1 を名指しする。
    $ps = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like ("*{0}\chain.ps1*" -f $r.n) -or
                             $_.CommandLine -like ("*{0}\run.ps1*"   -f $r.n) })
    $mp = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like ("*{0}*measure.py*" -f $r.n) })
    if ($ps.Count -gt 0 -or $mp.Count -gt 0) { break }

    $newest = $null
    foreach ($f in @((Join-Path $repo ("ml\{0}\measure.log" -f $r.n)),
                     (Join-Path $repo ("ml\{0}\chain.log"   -f $r.n)))) {
      if (Test-Path $f) {
        $t = (Get-Item $f).LastWriteTime
        if ($null -eq $newest -or $t -gt $newest) { $newest = $t }
      }
    }
    if ($null -ne $newest -and ((Get-Date) - $newest).TotalMinutes -lt 20) { break }

    if (-not $restarts.ContainsKey($r.n)) { $restarts[$r.n] = 0 }
    if ($restarts[$r.n] -ge 5) { Say ("WATCHDOG_ABORT {0} を5回起こしても続かない。手で見ること" -f $r.n); exit 1 }
    $restarts[$r.n]++
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
    Say ("WATCHDOG_RESTART {0} を {1} 回目の起こし直し（{2}）" -f $r.n, $restarts[$r.n], $r.starter)
    Start-Process -FilePath 'powershell.exe' `
      -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$r.starter `
      -WorkingDirectory $repo -WindowStyle Hidden
    break
  }
}
Say 'WATCHDOG_TIMEOUT 8時間たったので抜ける'
