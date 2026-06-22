# PullbackTrend v1.2 environment filter (MA200 slope) test - USDJPY H4
# Sweep slope threshold on both IS(2021-2026) and OOS(2016-2021)
# Ideal: OOS loss shrinks while IS profit holds

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "env_test_result.csv"

function Run-PB($from, $to, $useEnv, $slopeMin) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PullbackTrend""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  TrendMA_Period:          200`r`n  FastEMA_Period:          20`r`n  SlowEMA_Period:          50`r`n  RequireBullishCandle:    true`r`n  UsePullbackQuality:      true`r`n  UseMomentumConfirm:      true`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           22.5`r`n  UseTrendStrength:        $useEnv`r`n  MA_Slope_Lookback:       20`r`n  MA_Slope_Min_ATR:        $slopeMin`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           50`r`n  TakeProfit_Pips:         110`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260622`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""env_test""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\env_test_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\env_test_tmp.yaml --no-charts 2>&1 | Out-Null

    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return $null }
    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    $net=[double]$data["net_profit"]; $wt=[double]$data["win_trades"]; $lt=[double]$data["loss_trades"]
    $tr=[int]$data["total_trades"]; $pf=[double]$data["profit_factor"]; $dd=[double]$data["max_dd_pct"]
    $wr = if (($wt+$lt) -gt 0) { [math]::Round($wt/($wt+$lt)*100,1) } else { 0 }
    return [PSCustomObject]@{ Net=$net; WinRate=$wr; PF=$pf; DD=$dd; Trades=$tr }
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }
function Show($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-20} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-20} Net {1,9} | Win {2,5}% | PF {3,6} | DD {4,6}% | {5,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.PF, $r.DD, $r.Trades) -ForegroundColor $c
}

$slopes = @(0.3, 0.5, 0.8, 1.2)

Write-Host ""
Write-Host "=== IS 2021-2026 (optimized period) ===" -ForegroundColor Cyan
Show "Filter OFF (base)" (Run-PB "2021.06.21" "2026.06.20" "false" 0.5)
foreach ($s in $slopes) { Show "slope>=$s ATR" (Run-PB "2021.06.21" "2026.06.20" "true" $s) }

Write-Host ""
Write-Host "=== OOS 2016-2021 (unused / overfit check) ===" -ForegroundColor Cyan
Show "Filter OFF (base)" (Run-PB "2016.06.21" "2021.06.20" "false" 0.5)
foreach ($s in $slopes) { Show "slope>=$s ATR" (Run-PB "2016.06.21" "2021.06.20" "true" $s) }

Write-Host ""
Write-Host "Ideal: OOS loss shrinks while IS profit holds" -ForegroundColor Yellow
Write-Host "Done!" -ForegroundColor Green
