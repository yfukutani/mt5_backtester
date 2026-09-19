# fxqual10 を fxqual9 の後ろに繋ぐ（第20報）。
#
# **EA は触らない。** 使うのは既存 input（ScaFilMask / ScaFilRangeMin）だけなので、
# デプロイもコンパイルも行わない。fxqual9 がコンパイルしたバイナリをそのまま使う。
# したがって待つのは「fxqual9 が終わってロックが空き、テスターが居ないこと」だけ。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること。BOM無しだと PowerShell 5.1 が
#    ANSI として読み、日本語コメントが化けて構文エラーで即死する。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$lock = Join-Path $repo 'ml\fxmargin3\measure.lock'
$log  = Join-Path $repo 'ml\fxqual10\chain.log'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

function Busy {
  if (Get-Process metatester64 -ErrorAction SilentlyContinue) { return $true }
  if (-not (Test-Path $lock)) { return $false }
  $t = (Get-Content $lock -Raw -ErrorAction SilentlyContinue)
  if ($null -eq $t) { return $false }
  $t = $t.Trim()
  if ($t -notmatch '^\d+$') { return $false }
  return $null -ne (Get-Process -Id ([int]$t) -ErrorAction SilentlyContinue)
}

Say 'CHAIN_START(fxqual10) fxqual9 の完了とロックの解放を待つ（最大14時間）'

# fxqual9 はまだ走り出してすらいない（fxqualcfm の後ろで待機中）ので、
# 「measure.log がまだ無い」状態から始まる。**先に START を待つ**——
# それをしないと、cfm 完了直後の一瞬の空きを本ラウンドが横取りしてしまう。
$q9log = Join-Path $repo 'ml\fxqual9\measure.log'
$deadline = (Get-Date).AddHours(14)
$started = $false
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q9log) -and (Select-String -Path $q9log -Pattern 'FXQUAL9_START' -Quiet)) { $started = $true; break }
  # fxqual9 の chain 自体が死んでいたら、いつまでも START は出ない。
  if ((Test-Path (Join-Path $repo 'ml\fxqual9\chain.log')) -and
      (Select-String -Path (Join-Path $repo 'ml\fxqual9\chain.log') -Pattern 'CHAIN_ABORT' -Quiet)) {
    Say 'fxqual9 の chain が CHAIN_ABORT で降りた。待たずに進む'
    $started = $true
    break
  }
  Start-Sleep -Seconds 60
}
if (-not $started) { Say 'CHAIN_ABORT 14時間待っても fxqual9 が開始しなかった'; exit 1 }

# START が出たら、今度は END（か ABORT）とロック解放を待つ。
while ((Get-Date) -lt $deadline) {
  if ((Test-Path $q9log) -and (Select-String -Path $q9log -Pattern 'FXQUAL9_END|FXQUAL9_ABORT' -Quiet)) {
    if (-not (Busy)) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'CHAIN_ABORT 14時間待っても走れる状態にならなかった'; exit 1 }

# 並行セッションが先に取っているかもしれないので、空くまで粘る。
Start-Sleep -Seconds 30
$waited = 0
while ((Busy) -and $waited -lt 36000) { Start-Sleep -Seconds 60; $waited += 60 }
if (Busy) { Say 'CHAIN_ABORT ロックがずっと埋まっていた'; exit 1 }

Say 'FXQUAL10 を開始する（SCA UJ レンジ幅下限6点＋枠外し＋対照 × OOS/IS = 16run・EAは触らない）'
Set-Location $repo
& $py 'ml\fxqual10\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)
