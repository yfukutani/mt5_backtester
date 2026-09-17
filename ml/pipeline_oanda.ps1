# OANDA端末（BT1）で回すラウンドを1本のパイプラインに並べる（2026-09-17）。
#
# 【順序と理由】
#   1. fxoanda2（走行中）  上位候補を OANDAフィードで。P001/P002 は**4か月で口座が飛んだ**
#   2. fxoanda3            **OANDA で生き残る cap 水準はどこか**の掃引。第14報の宿題
#
# ロックは ml\fxoanda3\measure.lock と ml\fxoanda2\measure.lock（各ラウンド独立）。
# XM側のロック（ml\fxmargin3\measure.lock）とは別なので、XMのパイプラインと並行して走る。
# kill() は EXE のインストールフォルダで絞るので、片方のタイムアウトが他方を巻き添えにしない。
#
# ⚠️ このファイルは **UTF-8 BOM付き**で保存すること（PowerShell 5.1 は BOM無しを ANSI と読む）。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$log  = Join-Path $repo 'ml\pipeline_oanda.log'
$prevLog = Join-Path $repo 'ml\fxoanda2\measure.log'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

Say 'PIPELINE_START(oanda) fxoanda2 の完了を待って fxoanda3 を始める'
$deadline = (Get-Date).AddHours(12)
while ((Get-Date) -lt $deadline) {
  if (Test-Path $prevLog) {
    if (Select-String -Path $prevLog -Pattern 'FXOANDA2_END' -Quiet) { break }
  }
  Start-Sleep -Seconds 60
}
if ((Get-Date) -ge $deadline) { Say 'PIPELINE_ABORT fxoanda2 が12時間で終わらなかった'; exit 1 }

Start-Sleep -Seconds 30
Say 'FXOANDA3 を開始する（cap掃引・判定は「完走したか」が先）'
Set-Location $repo
& $py 'ml\fxoanda3\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("FXOANDA3 終了 exit={0}" -f $LASTEXITCODE)
Say 'PIPELINE_END(oanda)'
