# fxqual15 を起動する（第27報）。
#
# 🟢 **このラウンドは EA を一切触らない。コンパイルもデプロイもしない。**
#    `RsiTpMask_*` / `RsiTpMult_*` は第13ラウンドで実装済みで、`.ex5` はデプロイ済み。
#    使うのは既存 input だけなので、並行セッションの `ml/fxqual14` と
#    バイナリを取り合うことが構造的に起きない。待つのはテスターの排他だけである。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqual15\chain.log'

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
function Quiet { return (-not (LockBusy)) -and (-not (TesterBusy)) }

# 並行セッションの fxqual14（28run）が終わるのを待つ。完了は 23:30 頃の見込み。
Say 'CHAIN_START(fxqual15) fxqual14 の完了とロックの解放を待つ（最大8時間）'
$prev = Join-Path $repo 'ml\fxqual14\measure.log'
$deadline = (Get-Date).AddHours(8)
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $prev) -and (Select-String -Path $prev -Pattern 'FXQUAL14_END|FXQUAL14_ABORT' -Quiet)) {
    if (Quiet) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 8時間待っても走れる状態にならなかった'; exit 1 }

Start-Sleep -Seconds 30
$waited = 0
while ((-not (Quiet)) -and $waited -lt 3600) { Start-Sleep -Seconds 60; $waited += 60 }
if (-not (Quiet)) { Say 'CHAIN_ABORT ロック／テスターがずっと埋まっていた'; exit 1 }

# EA は触らないが、**第13ラウンドの .ex5 が載っていること**だけは確かめる。
# ここが崩れていると、MT5 が RsiTpMask_* を黙って無視して全案が対照と同値になる。
$experts  = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\BAC624F09E3C5D5AFDD21CE91C0B879D\MQL5\Experts'
$deployed = Join-Path $experts 'MIX_EA_SIMVERIFY.mq5'
$srcMq5   = Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5'
$hasTp = Select-String -Path $deployed -Pattern 'RsiTpFactor' -Quiet
$same  = ((Get-FileHash $deployed).Hash -eq (Get-FileHash $srcMq5).Hash)
Say ("DEPLOY_CHECK hasRsiTpFactor={0} sameAsRepo={1}（コンパイルはしない）" -f $hasTp, $same)
if (-not $hasTp) {
  Say 'CHAIN_ABORT デプロイ済みの EA に RsiTpFactor が無い。走らせても全案が対照と同値になる'
  exit 1
}
if (-not $same) {
  Say 'CHAIN_ABORT デプロイ済み .mq5 とリポジトリが食い違っている。誰かが EA を変えた。手で見ること'
  exit 1
}

Say 'FXQUAL15 を開始する（対照＋T001 の内点3点＋合成＋FULL・16run）'
Set-Location $repo
& $py 'ml\fxqual15\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
$code = $LASTEXITCODE
Say ("CHAIN_END exit={0}" -f $code)

$mlog = Join-Path $repo 'ml\fxqual15\measure.log'
$ok = (Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXQUAL15_END' -Quiet)
if (-not $ok) {
  Say 'FXQUAL15_END が無い。60秒待って1度だけ再開する'
  Start-Sleep -Seconds 60
  if (-not (LockBusy)) {
    & $py 'ml\fxqual15\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
    Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
  } else {
    Say 'CHAIN_RETRY_SKIP ロックが取られていた'
  }
}
