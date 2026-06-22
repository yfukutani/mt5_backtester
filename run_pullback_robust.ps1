# PullbackTrend 最適構成の年度別ロバスト性検証 — USDJPY H4
# ADX=22.5, ATR_SL=2.0 固定で RR2.0 vs RR3.0 を年度別比較
# 純利益最大が特定年への偏りでないか確認

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pb_robust_result.csv"

$years = 2021..2026

function Run-Year($year, $rr) {
    $fromDate = "${year}.01.01"
    $toDate   = if ($year -eq 2026) { "2026.06.20" } else { "${year}.12.31" }

    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PullbackTrend""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  TrendMA_Period:          200`r`n  FastEMA_Period:          20`r`n  SlowEMA_Period:          50`r`n  RequireBullishCandle:    true`r`n  UsePullbackQuality:      true`r`n  UseMomentumConfirm:      true`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           22.5`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                $rr`r`n  StopLoss_Pips:           30`r`n  TakeProfit_Pips:         45`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260622`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""PB_robust_${year}_RR${rr}""`r`n"

    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pb_robust_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pb_robust_tmp.yaml --no-charts 2>&1 | Out-Null

    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return $null }

    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    $net = [double]$data["net_profit"]
    $wt  = [double]$data["win_trades"]
    $lt  = [double]$data["loss_trades"]
    $tr  = [int]$data["total_trades"]
    $wr  = if (($wt+$lt) -gt 0) { [math]::Round($wt/($wt+$lt)*100,1) } else { 0 }
    return [PSCustomObject]@{ Net=$net; WinRate=$wr; Trades=$tr }
}

function Format-Profit($v) {
    $sign = if ($v -ge 0) { "+" } else { "" }
    return ("{0}{1:N0}" -f $sign, $v)
}

$rr20 = @{}; $rr30 = @{}
foreach ($year in $years) {
    Write-Host "[$year] RR2.0 ..." -ForegroundColor Cyan
    $rr20[$year] = Run-Year $year 2.0
    Write-Host ("  -> {0} ({1}% win, {2} tr)" -f (Format-Profit $rr20[$year].Net), $rr20[$year].WinRate, $rr20[$year].Trades)
    Write-Host "[$year] RR3.0 ..." -ForegroundColor Cyan
    $rr30[$year] = Run-Year $year 3.0
    Write-Host ("  -> {0} ({1}% win, {2} tr)" -f (Format-Profit $rr30[$year].Net), $rr30[$year].WinRate, $rr30[$year].Trades)
}

Write-Host ""
Write-Host "===== Robustness: RR2.0 vs RR3.0 (USDJPY H4, ADX22.5/ATR2.0) =====" -ForegroundColor Yellow
Write-Host ("{0,-6} {1,12} {2,8} {3,12} {4,8}" -f "Year","RR2.0_Net","Win%","RR3.0_Net","Win%")
Write-Host ("-" * 50)
$sum20 = 0; $sum30 = 0; $pos20 = 0; $pos30 = 0
foreach ($year in $years) {
    $n20 = $rr20[$year].Net; $n30 = $rr30[$year].Net
    $sum20 += $n20; $sum30 += $n30
    if ($n20 -ge 0) { $pos20++ }
    if ($n30 -ge 0) { $pos30++ }
    Write-Host ("{0,-6} {1,12} {2,7}% {3,12} {4,7}%" -f $year, (Format-Profit $n20), $rr20[$year].WinRate, (Format-Profit $n30), $rr30[$year].WinRate)
}
Write-Host ("-" * 50)
Write-Host ("{0,-6} {1,12} {2,8} {3,12}" -f "Sum", (Format-Profit $sum20), "", (Format-Profit $sum30))
Write-Host ("Profitable years: RR2.0 = $pos20/6 | RR3.0 = $pos30/6") -ForegroundColor White
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
