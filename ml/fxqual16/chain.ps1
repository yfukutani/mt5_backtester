# fxqual16 を起動する（第16ラウンド・倍率3 で cap を作っているのは誰か・8run）。
#
# 待つのは **fxqual15（並行セッション）の完走**とロックとテスター。
# fxqual14 → fxqual15 → fxqual16 の順に走る。
#
# ⚠️ EA は触らない。Mult_* / En_* は既存 input なのでデプロイもコンパイルも不要。
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。
$ErrorActionPreference = 'Continue'
$repo  = 'C:\Users\f\source\repos\mt5_backtester'
$py    = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock  = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log   = Join-Path $repo 'ml\fxqual16\chain.log'
$prev  = Join-Path $repo 'ml\fxqual15\measure.log'
$prev0 = Join-Path $repo 'ml\fxqual14\measure.log'

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
function TesterBusy { return $null -ne (Get-Process -Name 'metatester64' -ErrorAction SilentlyContinue) }
function Done([string]$p, [string]$tok) { return (Test-Path $p) -and (Select-String -Path $p -Pattern $tok -Quiet) }
function Quiet {
  return (Done $prev0 'FXQUAL14_END') -and (Done $prev 'FXQUAL15_END') -and
         (-not (LockBusy)) -and (-not (TesterBusy))
}

Say 'CHAIN_START(fxqual16) fxqual14 と fxqual15 の完走を待つ（最大8時間）'
$deadline = (Get-Date).AddHours(8)
while ((Get-Date) -lt $deadline) {
  if (Quiet) { break }
  Start-Sleep -Seconds 60
}
if (-not (Quiet)) { Say 'CHAIN_ABORT 8時間待っても空かなかった'; exit 1 }

Start-Sleep -Seconds 20
if (-not (Quiet)) { Say 'CHAIN_ABORT 待機後にロック／テスターが動いていた'; exit 1 }

Say 'FXQUAL16 を開始する（対照＋Pair抜き＋SCA_GJ重み0.25＋合成・8run・CAP_LOG あり）'
Set-Location $repo
& $py 'ml\fxqual16\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)

$mlog = Join-Path $repo 'ml\fxqual16\measure.log'
if (-not (Done $mlog 'FXQUAL16_END')) {
  Say 'FXQUAL16_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual16\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else {
    Say 'CHAIN_RETRY_SKIP ロックが取られていた'
  }
}
