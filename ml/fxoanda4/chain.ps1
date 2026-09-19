# fxoanda4 を起動する（第17ラウンド・OANDA BT1 端末）。
#
# 並行セッション（f87d4e）と合意した順番:
#   1. fxqual15（XM・走行中） -> 2. fxqual16（XM・4案） -> 3. **本チェーン**
#
# ゲートは3つとも満たすまで待つ:
#   (a) ml\fxqual16\chain.log に CHAIN_END か CHAIN_ABORT が出ている
#   (b) metatester64 が居ない
#   (c) **空き物理メモリ 8GB 以上**（FX 9枠 115か月の1テスターが 12.5GB 使う実測）
#
# 🔴 本チェーンは **OANDA 端末の EA だけ**を再コンパイルする。
#    XM 端末（BAC624...）には一切触らないので、並行セッションとバイナリを取り合わない。
#
# 警告: このファイルは UTF-8 BOM付きで保存すること（PS5.1 は BOM無しを CP932 で読む）。
$ErrorActionPreference = 'Continue'
$repo    = 'C:\Users\f\source\repos\mt5_backtester'
$py      = 'C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe'
$med     = 'C:\Program Files\OANDA MetaTrader 5_BT1\MetaEditor64.exe'
$experts = 'C:\Users\f\AppData\Roaming\MetaQuotes\Terminal\6142D304BFF2E6AB353977162D6F452C\MQL5\Experts'
$log     = Join-Path $repo 'ml\fxoanda4\chain.log'
$prevLog = Join-Path $repo 'ml\fxqual16\chain.log'

# ⚠️ ログは **BOM付き UTF-8** で始める。BOM が無いと PS5.1 の Get-Content が CP932 で読み、
#    あとから読むときに日本語が化ける（2026-09-19 に並行セッションが踏んだ事故と同じ形）。
function Say([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $m
  if (-not (Test-Path $log)) {
    [System.IO.File]::WriteAllText($log, '', (New-Object System.Text.UTF8Encoding($true)))
  }
  [System.IO.File]::AppendAllText($log, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
}
function TesterBusy { return $null -ne (Get-Process -Name 'metatester64' -ErrorAction SilentlyContinue) }
function FreeGB { return (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB }
function PrevDone {
  if (-not (Test-Path $prevLog)) { return $false }
  return (Select-String -Path $prevLog -Pattern 'CHAIN_END|CHAIN_ABORT' -Quiet)
}
function Ready { return (PrevDone) -and (-not (TesterBusy)) -and ((FreeGB) -ge 8.0) }

Say 'CHAIN_START(fxoanda4) fxqual16 の終了・テスター不在・空き8GB を待つ（最大8時間）'
$deadline = (Get-Date).AddHours(8)
$ok = $false
while ((Get-Date) -lt $deadline) {
  if (Ready) {
    Start-Sleep -Seconds 60
    if (Ready) { $ok = $true; break }
  }
  Start-Sleep -Seconds 60
}
if (-not $ok) { Say 'CHAIN_ABORT 8時間待っても条件がそろわなかった。EAは触らない'; exit 1 }
Say ('GATE_OK freeGB={0:N1}' -f (FreeGB))

# --- デプロイとコンパイル（OANDA 端末のみ）---------------------------------
# ⚠️ ここを飛ばすと静かに嘘の実測が残る。OANDA 端末の .ex5 は 2026-09-18 の古い版で、
#    RsiTpMask_* も ScaRR_* も持っていない。MT5 は知らない input を黙って無視するので、
#    O020/O021/O022 が O000 と完全同値になり「効かなかった」という結論に化ける。
$srcMq5     = Join-Path $repo 'experts\MIX_EA_SIMVERIFY.mq5'
$deployed   = Join-Path $experts 'MIX_EA_SIMVERIFY.mq5'
$deployedEx = Join-Path $experts 'MIX_EA_SIMVERIFY.ex5'

foreach ($tok in @('RsiTpMask_UJ','RsiTpMask_EU','RsiTpMult_UJ','RsiTpFactor','ScaFilRangeMin','MarginCapPct')) {
  if (-not (Select-String -Path $srcMq5 -Pattern $tok -Quiet)) {
    Say ("CHAIN_ABORT リポジトリの .mq5 に {0} が無い" -f $tok); exit 1
  }
}
if (-not (Test-Path $med)) { Say ("CHAIN_ABORT MetaEditor が無い: {0}" -f $med); exit 1 }

# 古い .ex5 を退避しておく（再現が必要になったとき用）
if (Test-Path $deployedEx) {
  Copy-Item $deployedEx (Join-Path $experts 'MIX_EA_SIMVERIFY.20260918.ex5.bak') -Force
  Say 'BACKUP 旧 .ex5 を MIX_EA_SIMVERIFY.20260918.ex5.bak へ退避した'
}

Copy-Item $srcMq5 $deployed -Force
$clog = Join-Path $experts 'c_oanda_r17.log'
& $med ('/compile:' + $deployed) ('/log:' + $clog)
Start-Sleep -Seconds 5
$text = ''
if (Test-Path $clog) { $text = [System.Text.Encoding]::Unicode.GetString([System.IO.File]::ReadAllBytes($clog)) }
$res = ($text -split "`r?`n" | Where-Object { $_ -match '^Result:' } | Select-Object -Last 1)
Say ("COMPILE {0}" -f $res)
if ($res -notmatch '0 errors') { Say 'CHAIN_ABORT コンパイルに失敗した。走らせない'; exit 1 }

$hasA  = Select-String -Path $deployed -Pattern 'RsiTpMask_UJ' -Quiet
$hasB  = Select-String -Path $deployed -Pattern 'ScaFilRangeMin' -Quiet
$same  = ((Get-FileHash $deployed).Hash -eq (Get-FileHash $srcMq5).Hash)
$fresh = ((Get-Item $deployedEx).LastWriteTime -ge (Get-Item $deployed).LastWriteTime)
Say ("DEPLOY_CHECK hasRsiTp={0} hasScaFil={1} sameSrc={2} freshEx={3}" -f $hasA,$hasB,$same,$fresh)
if (-not ($hasA -and $hasB -and $same -and $fresh)) { Say 'CHAIN_ABORT デプロイ検査に落ちた'; exit 1 }

Say 'FXOANDA4 を開始する（15 job・O000 の回帰が先頭）'
Set-Location $repo
& $py 'ml\fxoanda4\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
Say ("CHAIN_END exit={0}" -f $LASTEXITCODE)

$mlog = Join-Path $repo 'ml\fxoanda4\measure.log'
$done = (Test-Path $mlog) -and (Select-String -Path $mlog -Pattern 'FXOANDA4_END' -Quiet)
if (-not $done) {
  Say 'FXOANDA4_END が無い。60秒待って1度だけ再開する（完了済みの job は飛ばされる）'
  Start-Sleep -Seconds 60
  & $py 'ml\fxoanda4\measure.py' 2>&1 | Add-Content -Path $log -Encoding utf8
  Say ("CHAIN_RETRY_END exit={0}" -f $LASTEXITCODE)
}
