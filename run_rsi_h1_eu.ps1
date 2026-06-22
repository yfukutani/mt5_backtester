# RSI_Reversal range filter on H1 charts - USDJPY H1 & EURUSD H1, full period
# Find best range threshold per chart (full 2016-2026), then yearly for best.

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"

$charts = @(
    [ordered]@{ name="USDJPY_H1"; sym="USDJPY"; magic=20260604; csv="r3_h1.csv" },
    [ordered]@{ name="EURUSD_H1"; sym="EURUSD"; magic=20260605; csv="r3_eu.csv" }
)

function Run-Chart($chart, $from, $to, $useRange, $rangeMax) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""RSI_Reversal""`r`nsymbol:    ""$($chart.sym)""`r`nperiod:    ""H1""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  MA_Period:               200`r`n  BB_Period:               20`r`n  BB_Deviation:            2.5`r`n  RSI_Period:              14`r`n  RSI_OverboughtExtreme:   75.0`r`n  RSI_Overbought:          72.5`r`n  RSI_OversoldExtreme:     27.5`r`n  RSI_Oversold:            30.0`r`n  UseDoublePattern:        false`r`n  Swing_Lookback:          3`r`n  DP_Pattern_Bars:         60`r`n  DP_Tolerance_ATR:        0.5`r`n  UseRangeFilter:          $useRange`r`n  Range_Slope_Lookback:    20`r`n  Range_Slope_Max_ATR:     $rangeMax`r`n  UseTrailingStop:         false`r`n  UseBreakeven:            false`r`n  UseVolatilityFilter:     false`r`n  UseATRStopLoss:          false`r`n  UseADXFilter:            false`r`n  UseTimeFilter:           false`r`n  LotSize:                 0.01`r`n  StopLoss_Pips:           45`r`n  TakeProfit_Pips:         105`r`n  MagicNumber:             $($chart.magic)`r`n  ResultFileName:          ""$($chart.csv)""`r`nreport_dir:  ""results""`r`nreport_name: ""r3""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\r3_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\r3_tmp.yaml --no-charts 2>&1 | Out-Null
    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $chart.csv -ErrorAction SilentlyContinue | Select-Object -First 1
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
    if ($null -eq $r) { Write-Host ("  {0,-16} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-16} Net {1,9} | Win {2,5}% | PF {3,6} | DD {4,5:N1}% | {5,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.PF, $r.DD, $r.Trades) -ForegroundColor $c
}

$full_from = "2016.01.01"; $full_to = "2026.06.20"
$variants = @(
    [ordered]@{ label="OFF";        ur="false"; rg=0.3 },
    [ordered]@{ label="range<=0.2"; ur="true";  rg=0.2 },
    [ordered]@{ label="range<=0.3"; ur="true";  rg=0.3 },
    [ordered]@{ label="range<=0.4"; ur="true";  rg=0.4 }
)

foreach ($chart in $charts) {
    Write-Host ""
    Write-Host ("=== {0} (full period 2016-2026) ===" -f $chart.name) -ForegroundColor Cyan
    foreach ($v in $variants) {
        Show $v.label (Run-Chart $chart $full_from $full_to $v.ur $v.rg)
    }
}

Write-Host ""
Write-Host "Combined with USDJPY H4 (BB2.5 range<=0.2 = +10,032) for 3-chart robust portfolio" -ForegroundColor Yellow
Write-Host "Done!" -ForegroundColor Green
