# PullbackTrend 深掘り検証 — OOS（過学習チェック）+ 別銘柄H4探索
# 最適構成固定: ADX22.5 / ATR_SL2.0 / RR2.0 / 全改善ON

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pb_deep_result.csv"

function Run-PB($symbol, $from, $to) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PullbackTrend""`r`nsymbol:    ""$symbol""`r`nperiod:    ""H4""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  TrendMA_Period:          200`r`n  FastEMA_Period:          20`r`n  SlowEMA_Period:          50`r`n  RequireBullishCandle:    true`r`n  UsePullbackQuality:      true`r`n  UseMomentumConfirm:      true`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           22.5`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           50`r`n  TakeProfit_Pips:         110`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260622`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""PB_deep""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pb_deep_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pb_deep_tmp.yaml --no-charts 2>&1 | Out-Null

    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return $null }
    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    $net=[double]$data["net_profit"]; $gp=[double]$data["gross_profit"]; $gl=[math]::Abs([double]$data["gross_loss"])
    $wt=[double]$data["win_trades"]; $lt=[double]$data["loss_trades"]; $tr=[int]$data["total_trades"]
    $pf=[double]$data["profit_factor"]; $dd=[double]$data["max_dd_pct"]
    $wr = if (($wt+$lt) -gt 0) { [math]::Round($wt/($wt+$lt)*100,1) } else { 0 }
    $aw = if ($wt -gt 0) { $gp/$wt } else { 0 }
    $al = if ($lt -gt 0) { $gl/$lt } else { 0 }
    $eff = if ($al -gt 0) { [math]::Round($aw/$al,2) } else { 0 }
    return [PSCustomObject]@{ Net=$net; WinRate=$wr; EffRR=$eff; PF=$pf; DD=$dd; Trades=$tr }
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }
function Show($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-20} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-20} Net {1,9} | Win {2,5}% | EffRR {3,5} | PF {4,6} | DD {5,5}% | {6,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.EffRR, $r.PF, $r.DD, $r.Trades) -ForegroundColor $c
}

# === Part A: OOS検証（USDJPY H4、最適化期間の前後で比較）===
Write-Host ""
Write-Host "=== Part A: OOS過学習チェック (USDJPY H4) ===" -ForegroundColor Cyan
$is  = Run-PB "USDJPY" "2021.06.21" "2026.06.20"
$oos = Run-PB "USDJPY" "2016.06.21" "2021.06.20"
Show "IS  2021-2026(最適化)" $is
Show "OOS 2016-2021(未使用)" $oos

# === Part B: 別銘柄H4探索（過去5年）===
Write-Host ""
Write-Host "=== Part B: 別銘柄H4 探索 (2021.06-2026.06) ===" -ForegroundColor Cyan
$symbols = @("USDJPY","GBPJPY","EURJPY","AUDJPY","EURUSD","GBPUSD")
$symResults = @{}
foreach ($sym in $symbols) {
    $r = Run-PB $sym "2021.06.21" "2026.06.20"
    $symResults[$sym] = $r
    Show $sym $r
}

# === ポートフォリオ候補（プラス銘柄の合算）===
Write-Host ""
Write-Host "=== プラス銘柄サマリー ===" -ForegroundColor Yellow
$posSum = 0; $posSyms = @()
foreach ($sym in $symbols) {
    if ($symResults[$sym] -and $symResults[$sym].Net -gt 0) {
        $posSum += $symResults[$sym].Net
        $posSyms += $sym
    }
}
Write-Host ("  プラス銘柄: {0}" -f ($posSyms -join ", "))
Write-Host ("  合算純利益: {0} JPY" -f (Format-Profit $posSum)) -ForegroundColor Green
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
