# PullbackTrend v1.1 年度別検証 — RR2.0軸（期待値最優先）
# 構成: 4改善ON + RR2.0 / H4の3銘柄（USDJPY, EURUSD, GBPUSD）
# 期間: 2021-2026（過去5年）

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"

$years = 2021..2026

$charts = @(
    [ordered]@{ label="USDJPY_H4"; symbol="USDJPY"; magic=20260622; csvName="pby_usdjpy_result.csv" },
    [ordered]@{ label="EURUSD_H4"; symbol="EURUSD"; magic=20260623; csvName="pby_eurusd_result.csv" },
    [ordered]@{ label="GBPUSD_H4"; symbol="GBPUSD"; magic=20260624; csvName="pby_gbpusd_result.csv" }
)

$allResults = @{}
foreach ($year in $years) { $allResults[$year] = @{} }

foreach ($year in $years) {
    $fromDate = "${year}.01.01"
    $toDate   = if ($year -eq 2026) { "2026.06.20" } else { "${year}.12.31" }

    foreach ($chart in $charts) {
        $label = $chart.label
        Write-Host "[$year] $label ..." -ForegroundColor Cyan

        $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PullbackTrend""`r`nsymbol:    ""$($chart.symbol)""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  TrendMA_Period:          200`r`n  FastEMA_Period:          20`r`n  SlowEMA_Period:          50`r`n  RequireBullishCandle:    true`r`n  UsePullbackQuality:      true`r`n  UseMomentumConfirm:      true`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           25.0`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             1.5`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           30`r`n  TakeProfit_Pips:         45`r`n  LotSize:                 0.01`r`n  MagicNumber:             $($chart.magic)`r`n  ResultFileName:          ""$($chart.csvName)""`r`nreport_dir:  ""results""`r`nreport_name: ""PBY_$($label)_${year}""`r`n"

        [System.IO.File]::WriteAllText(
            "C:\Users\f\source\repos\mt5_backtester\configs\pby_tmp.yaml",
            $yaml,
            [System.Text.Encoding]::UTF8
        )

        & $mt5bt run configs\pby_tmp.yaml --no-charts 2>&1 | Out-Null

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

function Format-Profit($v) {
    $sign = if ($v -ge 0) { "+" } else { "" }
    return ("{0}{1:N0}" -f $sign, $v)
}

Write-Host ""
Write-Host "===== PullbackTrend RR2.0 Yearly (H4 x3 symbols, 2021-2026) =====" -ForegroundColor Yellow
Write-Host ("{0,-6} {1,12} {2,12} {3,12} {4,10}" -f "Year","USDJPY_H4","EURUSD_H4","GBPUSD_H4","Total")
Write-Host ("-" * 56)

$grandTotal = 0
$symTotals = @{ USDJPY_H4=0; EURUSD_H4=0; GBPUSD_H4=0 }
foreach ($year in $years) {
    $u = $allResults[$year]["USDJPY_H4"].profit
    $e = $allResults[$year]["EURUSD_H4"].profit
    $g = $allResults[$year]["GBPUSD_H4"].profit
    $total = $u + $e + $g
    $grandTotal += $total
    $symTotals.USDJPY_H4 += $u
    $symTotals.EURUSD_H4 += $e
    $symTotals.GBPUSD_H4 += $g
    $color = if ($total -ge 0) { "Green" } else { "Red" }
    Write-Host ("{0,-6} {1,12} {2,12} {3,12} {4,10}" -f $year, (Format-Profit $u), (Format-Profit $e), (Format-Profit $g), (Format-Profit $total)) -ForegroundColor $color
}
Write-Host ("-" * 56)
Write-Host ("{0,-6} {1,12} {2,12} {3,12} {4,10}" -f "Sum", (Format-Profit $symTotals.USDJPY_H4), (Format-Profit $symTotals.EURUSD_H4), (Format-Profit $symTotals.GBPUSD_H4), (Format-Profit $grandTotal))

# 勝率平均
Write-Host ""
Write-Host "Win rate by symbol (avg across years):" -ForegroundColor Yellow
foreach ($lbl in @("USDJPY_H4","EURUSD_H4","GBPUSD_H4")) {
    $wrs = @()
    foreach ($year in $years) { $wrs += $allResults[$year][$lbl].winRate }
    $avgWr = [math]::Round(($wrs | Measure-Object -Average).Average, 1)
    Write-Host ("  {0}: {1}%" -f $lbl, $avgWr)
}

$gColor = if ($grandTotal -ge 0) { "Green" } else { "Red" }
Write-Host ""
Write-Host ("GRAND TOTAL (5yr, 3 symbols): {0} JPY" -f (Format-Profit $grandTotal)) -ForegroundColor $gColor
Write-Host "Done!" -ForegroundColor Green
