# Volatility filter (ATR min) yearly backtest 2016-2026
# H4: ATR_Min_Pips=25 / H1+EU: ATR_Min_Pips=8

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"

$years = 2016..2026

$charts = @(
    [ordered]@{ label="USDJPY_H4"; symbol="USDJPY"; period="H4"; sl=50; tp=110; useDP="true";  dpBars=100; magic=20260610; csvName="vol_h4_result.csv"; atrMin=25.0 },
    [ordered]@{ label="USDJPY_H1"; symbol="USDJPY"; period="H1"; sl=45; tp=105; useDP="false"; dpBars=60;  magic=20260604; csvName="vol_h1_result.csv"; atrMin=8.0  },
    [ordered]@{ label="EURUSD_H1"; symbol="EURUSD"; period="H1"; sl=45; tp=105; useDP="false"; dpBars=60;  magic=20260605; csvName="vol_eu_result.csv"; atrMin=8.0  }
)

$allResults = @{}
foreach ($year in $years) { $allResults[$year] = @{} }

foreach ($year in $years) {
    $fromDate = "${year}.01.01"
    $toDate   = if ($year -eq 2026) { "2026.06.20" } else { "${year}.12.31" }

    foreach ($chart in $charts) {
        $label      = $chart.label
        $reportName = "VOL_${label}_${year}"

        Write-Host "[$year] $label (ATR>=$($chart.atrMin)pips) ..." -ForegroundColor Cyan

        $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""RSI_Reversal""`r`nsymbol:    ""$($chart.symbol)""`r`nperiod:    ""$($chart.period)""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  MA_Period:               200`r`n  BB_Period:               20`r`n  BB_Deviation:            2.5`r`n  RSI_Period:              14`r`n  RSI_OverboughtExtreme:   75.0`r`n  RSI_Overbought:          72.5`r`n  RSI_OversoldExtreme:     27.5`r`n  RSI_Oversold:            30.0`r`n  UseDoublePattern:        $($chart.useDP)`r`n  Swing_Lookback:          3`r`n  DP_Pattern_Bars:         $($chart.dpBars)`r`n  DP_Tolerance_ATR:        0.5`r`n  UseVolatilityFilter:     true`r`n  ATR_Min_Pips:            $($chart.atrMin)`r`n  UseTimeFilter:           false`r`n  FilterStartHour:         8`r`n  FilterEndHour:           20`r`n  UseATRStopLoss:          false`r`n  ATR_SL_Multiplier:       1.5`r`n  ATR_RR_Ratio:            2.0`r`n  UseADXFilter:            false`r`n  ADX_Period:              14`r`n  ADX_Threshold:           25.0`r`n  LotSize:                 0.01`r`n  StopLoss_Pips:           $($chart.sl)`r`n  TakeProfit_Pips:         $($chart.tp)`r`n  MagicNumber:             $($chart.magic)`r`n  ResultFileName:          ""$($chart.csvName)""`r`nreport_dir:  ""results""`r`nreport_name: ""$reportName""`r`n"

        [System.IO.File]::WriteAllText(
            "C:\Users\f\source\repos\mt5_backtester\configs\vol_filter_tmp.yaml",
            $yaml,
            [System.Text.Encoding]::UTF8
        )

        & $mt5bt run configs\vol_filter_tmp.yaml --no-charts 2>&1 | Out-Null

        $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $chart.csvName -ErrorAction SilentlyContinue | Select-Object -First 1

        $netProfit = 0; $trades = 0; $winRate = 0

        if ($csvFile -and (Test-Path $csvFile.FullName)) {
            $data = @{}
            Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
                $parts = $_ -split ','
                if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
            }
            $netProfit = [double]$data["net_profit"]
            $trades    = [int]$data["total_trades"]
            $wt = [double]$data["win_trades"]
            $lt = [double]$data["loss_trades"]
            if (($wt + $lt) -gt 0) { $winRate = [math]::Round($wt / ($wt + $lt) * 100, 1) }
            $sign  = if ($netProfit -ge 0) { "+" } else { "" }
            $color = if ($netProfit -ge 0) { "Green" } else { "Red" }
            Write-Host ("  -> {0}{1:N0} JPY  {2} trades  {3}% win" -f $sign, $netProfit, $trades, $winRate) -ForegroundColor $color
        } else {
            Write-Host "  -> CSV not found" -ForegroundColor Yellow
        }

        $allResults[$year][$label] = @{ profit=$netProfit; trades=$trades; winRate=$winRate }
    }
}

# Baseline (fixed SL, no filter)
$baseline = @{
    2016=@{h4=-2729;  h1=12703;  eu=-2975};  2017=@{h4=-6855;  h1=-3219; eu=127};
    2018=@{h4=-4118;  h1=-4270;  eu=-3668};  2019=@{h4=1416;   h1=-9361; eu=485};
    2020=@{h4=-4416;  h1=-8285;  eu=-6000};  2021=@{h4=-5911;  h1=-6890; eu=-528};
    2022=@{h4=-780;   h1=2523;   eu=-7922};  2023=@{h4=3434;   h1=532;   eu=7056};
    2024=@{h4=13072;  h1=11089;  eu=6581};   2025=@{h4=-6400;  h1=-5247; eu=7213};
    2026=@{h4=4760;   h1=3851;   eu=-9542}
}

function Format-Profit($v) {
    $sign = if ($v -ge 0) { "+" } else { "" }
    return ("{0}{1:N0}" -f $sign, $v)
}

Write-Host ""
Write-Host "===== VolFilter Yearly Results (H4>=25pips, H1/EU>=8pips) =====" -ForegroundColor Yellow
Write-Host ("{0,-6} {1,12} {2,12} {3,12} {4,10} {5,10}" -f "Year","USDJPY_H4","USDJPY_H1","EURUSD_H1","VOL-Total","Base-Total")
Write-Host ("-" * 66)

$grandVol  = 0
$grandBase = 0
foreach ($year in $years) {
    $h4    = $allResults[$year]["USDJPY_H4"].profit
    $h1    = $allResults[$year]["USDJPY_H1"].profit
    $eu    = $allResults[$year]["EURUSD_H1"].profit
    $total = $h4 + $h1 + $eu
    $base  = $baseline[$year].h4 + $baseline[$year].h1 + $baseline[$year].eu
    $grandVol  += $total
    $grandBase += $base
    $lineColor = if ($total -gt $base) { "Green" } else { "White" }
    Write-Host ("{0,-6} {1,12} {2,12} {3,12} {4,10} {5,10}" -f $year, (Format-Profit $h4), (Format-Profit $h1), (Format-Profit $eu), (Format-Profit $total), (Format-Profit $base)) -ForegroundColor $lineColor
}

Write-Host ("-" * 66)
$diffTotal = $grandVol - $grandBase
Write-Host ("Grand  {0,45} {1,10}" -f (Format-Profit $grandVol), (Format-Profit $grandBase))
$diffColor = if ($diffTotal -ge 0) { "Green" } else { "Red" }
Write-Host ("Diff vs Base: {0}" -f (Format-Profit $diffTotal)) -ForegroundColor $diffColor
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
