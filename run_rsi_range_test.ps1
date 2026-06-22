# RSI_Reversal v2.9 range filter test - 3 charts, yearly 2016-2026
# Sweep slope threshold (range = MA200 slope small). Compare to OFF baseline.
# Goal: does range filter cut the trend-period losses (e.g. 2022 yen-trend)?

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"

# 3-chart config: USDJPY H4 (DP on), USDJPY H1, EURUSD H1
$charts = @(
    [ordered]@{ sym="USDJPY"; tf="H4"; dp="true";  dpb=100; sl=50; tp=110; magic=20260610; csv="rng_h4.csv" },
    [ordered]@{ sym="USDJPY"; tf="H1"; dp="false"; dpb=60;  sl=45; tp=105; magic=20260604; csv="rng_h1.csv" },
    [ordered]@{ sym="EURUSD"; tf="H1"; dp="false"; dpb=60;  sl=45; tp=105; magic=20260605; csv="rng_eu.csv" }
)

function Run-Chart($chart, $from, $to, $useRange, $slopeMax) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""RSI_Reversal""`r`nsymbol:    ""$($chart.sym)""`r`nperiod:    ""$($chart.tf)""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  MA_Period:               200`r`n  BB_Period:               20`r`n  BB_Deviation:            2.5`r`n  RSI_Period:              14`r`n  RSI_OverboughtExtreme:   75.0`r`n  RSI_Overbought:          72.5`r`n  RSI_OversoldExtreme:     27.5`r`n  RSI_Oversold:            30.0`r`n  UseDoublePattern:        $($chart.dp)`r`n  Swing_Lookback:          3`r`n  DP_Pattern_Bars:         $($chart.dpb)`r`n  DP_Tolerance_ATR:        0.5`r`n  UseRangeFilter:          $useRange`r`n  Range_Slope_Lookback:    20`r`n  Range_Slope_Max_ATR:     $slopeMax`r`n  UseTrailingStop:         false`r`n  UseBreakeven:            false`r`n  UseVolatilityFilter:     false`r`n  UseATRStopLoss:          false`r`n  UseADXFilter:            false`r`n  UseTimeFilter:           false`r`n  LotSize:                 0.01`r`n  StopLoss_Pips:           $($chart.sl)`r`n  TakeProfit_Pips:         $($chart.tp)`r`n  MagicNumber:             $($chart.magic)`r`n  ResultFileName:          ""$($chart.csv)""`r`nreport_dir:  ""results""`r`nreport_name: ""rng_test""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\rng_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\rng_tmp.yaml --no-charts 2>&1 | Out-Null
    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $chart.csv -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return 0 }
    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    return [double]$data["net_profit"]
}

function Run-Year-3chart($year, $useRange, $slopeMax) {
    $from = "$year.01.01"; $to = if ($year -eq 2026) { "2026.06.20" } else { "$year.12.31" }
    $sum = 0
    foreach ($c in $charts) { $sum += (Run-Chart $c $from $to $useRange $slopeMax) }
    return $sum
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }

$years = 2016..2026

# Configs to compare
$variants = @(
    [ordered]@{ label="OFF (base)"; useRange="false"; slope=0.5 },
    [ordered]@{ label="range<=0.3";  useRange="true";  slope=0.3 },
    [ordered]@{ label="range<=0.5";  useRange="true";  slope=0.5 },
    [ordered]@{ label="range<=0.8";  useRange="true";  slope=0.8 }
)

$totals = @{}
foreach ($v in $variants) {
    Write-Host ("=== {0} ===" -f $v.label) -ForegroundColor Cyan
    $tot = 0
    foreach ($y in $years) {
        $n = Run-Year-3chart $y $v.useRange $v.slope
        $tot += $n
        Write-Host ("  $y : {0}" -f (Format-Profit $n))
    }
    $totals[$v.label] = $tot
    Write-Host ("  TOTAL: {0}" -f (Format-Profit $tot)) -ForegroundColor White
}

Write-Host ""
Write-Host "=== Summary (3-chart total, 2016-2026) ===" -ForegroundColor Yellow
foreach ($v in $variants) {
    $c = if ($totals[$v.label] -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-12} {1}" -f $v.label, (Format-Profit $totals[$v.label])) -ForegroundColor $c
}
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
