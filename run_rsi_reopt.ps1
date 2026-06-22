# RSI_Reversal full-period re-optimization - USDJPY H4 (DP), 2016-2026
# Find params that are profitable over the full 10 years (with range filter ON).
# Individual sweeps: BB deviation, range threshold, SL/TP.

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "reopt_result.csv"

$fromDate = "2016.01.01"
$toDate   = "2026.06.20"

function Run-RSI($bbDev, $useRange, $rangeMax, $sl, $tp) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""RSI_Reversal""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  MA_Period:               200`r`n  BB_Period:               20`r`n  BB_Deviation:            $bbDev`r`n  RSI_Period:              14`r`n  RSI_OverboughtExtreme:   75.0`r`n  RSI_Overbought:          72.5`r`n  RSI_OversoldExtreme:     27.5`r`n  RSI_Oversold:            30.0`r`n  UseDoublePattern:        true`r`n  Swing_Lookback:          3`r`n  DP_Pattern_Bars:         100`r`n  DP_Tolerance_ATR:        0.5`r`n  UseRangeFilter:          $useRange`r`n  Range_Slope_Lookback:    20`r`n  Range_Slope_Max_ATR:     $rangeMax`r`n  UseTrailingStop:         false`r`n  UseBreakeven:            false`r`n  UseVolatilityFilter:     false`r`n  UseATRStopLoss:          false`r`n  UseADXFilter:            false`r`n  UseTimeFilter:           false`r`n  LotSize:                 0.01`r`n  StopLoss_Pips:           $sl`r`n  TakeProfit_Pips:         $tp`r`n  MagicNumber:             20260610`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""reopt""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\reopt_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\reopt_tmp.yaml --no-charts 2>&1 | Out-Null
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
    if ($null -eq $r) { Write-Host ("  {0,-18} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-18} Net {1,9} | Win {2,5}% | PF {3,6} | DD {4,5:N1}% | {5,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.PF, $r.DD, $r.Trades) -ForegroundColor $c
}

Write-Host ""
Write-Host "=== Baseline (current params, full period) ===" -ForegroundColor Cyan
Show "RangeOFF BB2.5" (Run-RSI 2.5 "false" 0.3 50 110)
Show "RangeON  BB2.5" (Run-RSI 2.5 "true"  0.3 50 110)

Write-Host ""
Write-Host "=== Sweep 1: BB deviation (range<=0.3, SL50/TP110) ===" -ForegroundColor Cyan
foreach ($bb in @(2.0, 2.5, 3.0)) { Show ("BB=$bb") (Run-RSI $bb "true" 0.3 50 110) }

Write-Host ""
Write-Host "=== Sweep 2: range threshold (BB2.5, SL50/TP110) ===" -ForegroundColor Cyan
foreach ($rg in @(0.2, 0.3, 0.4)) { Show ("range<=$rg") (Run-RSI 2.5 "true" $rg 50 110) }

Write-Host ""
Write-Host "=== Sweep 3: SL/TP (BB2.5, range<=0.3) ===" -ForegroundColor Cyan
Show "SL40/TP80(RR2)"   (Run-RSI 2.5 "true" 0.3 40 80)
Show "SL50/TP100(RR2)"  (Run-RSI 2.5 "true" 0.3 50 100)
Show "SL50/TP110(RR2.2)" (Run-RSI 2.5 "true" 0.3 50 110)
Show "SL60/TP90(RR1.5)" (Run-RSI 2.5 "true" 0.3 60 90)
Show "SL40/TP100(RR2.5)" (Run-RSI 2.5 "true" 0.3 40 100)

Write-Host ""
Write-Host "Question: any config profitable over full 10yr?" -ForegroundColor Yellow
Write-Host "Done!" -ForegroundColor Green
