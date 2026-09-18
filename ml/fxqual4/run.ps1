# fxqual4 を回すだけの起動スクリプト（第17報）。
#
# 【fxqual3 の chain.ps1 との違い】
# fxqual4 は **新しい input を1つも使わない**。`PbSlopeATR_UJ/_GJ` と
# `PbAdxThr_UJ/_GJ` は第14報で既に EA に入っていて、いま端末に置かれている
# `.ex5`（fxqual3 のために chain.ps1 がコンパイルしたもの）がそのまま受け付ける。
# したがって **デプロイもコンパイルも行わない**。EA を触らないので回帰リスクがゼロである。
# W000 が fxqual3 の V000 と1円まで一致することが、その実測になる。
#
# ⚠️ このファイルは UTF-8 BOM付きで保存すること（PS5.1 が ANSI として読むと即死する）。
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\f\source\repos\mt5_backtester'
$py   = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$log  = Join-Path $repo 'ml\fxqual4\chain.log'

function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  Add-Content -Path $log -Value $line -Encoding utf8
}

Say 'RUN_START(fxqual4) PB 入口を締める7案＋対照（16run・EAは触らない）'
Set-Location $repo
& $py 'ml\fxqual4\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("RUN_END exit={0}" -f $LASTEXITCODE)
