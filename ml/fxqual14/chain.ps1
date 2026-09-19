# fxqual14 を起動する（第26報）。fxqual13 の完走を待ってから走る。
#
# ⚠️ このラウンドは EA を書き換えない（En_* は既存 input）。
#    したがってデプロイもコンパイルもしない。待つのはロックとテスターだけ。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqual14\chain.log'
$prev = Join-Path $repo 'ml\fxqual13\measure.log'

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
function PrevDone { return (Test-Path $prev) -and (Select-String -Path $prev -Pattern 'FXQUAL13_END' -Quiet) }
function Quiet { return (PrevDone) -and (-not (LockBusy)) -and (-not (TesterBusy)) }

Say 'CHAIN_START(fxqual14) fxqual13 の完走とロック解放を待つ（最大4時間）'
$deadline = (Get-Date).AddHours(4)
while ((Get-Date) -lt $deadline) {
  if (Quiet) { break }
  Start-Sleep -Seconds 60
}
if (-not (Quiet)) { Say 'CHAIN_ABORT 4時間待っても空かなかった'; exit 1 }

Start-Sleep -Seconds 20
if (-not (Quiet)) { Say 'CHAIN_ABORT 待機後にロック／テスターが動いていた'; exit 1 }

Say 'FXQUAL14 を開始する（回帰2＋Carry 3＋倍率3 の対＋LOSO 8枠・28run・CAP_LOG あり）'
Set-Location $repo
& $py 'ml\fxqual14\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
$code = $LASTEXITCODE
Say ("CHAIN_END exit={0}" -f $code)

$mlog = Join-Path $repo 'ml\fxqual14\measure.log'
$ok = (Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUAL14_END' -Quiet)
if (-not $ok) {
  Say 'FXQUAL14_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual14\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else {
    Say 'CHAIN_RETRY_SKIP ロックが取られていた'
  }
}
