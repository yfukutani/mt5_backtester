# PullbackTrend v1.1 構成比較（USDJPY H4, 過去5年 2021.06.21-2026.06.20）

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pb_compare_h4_result.csv"

$fromDate = "2021.06.21"
$toDate   = "2026.06.20"
$symbol   = "USDJPY"
$period   = "H4"

$configs = @(
    [ordered]@{ name="C0_baseline(allOFF)"; quality="false"; momentum="false"; adx="false"; rr=1.5 },
    [ordered]@{ name="C4_all_ON";           quality="true";  momentum="true";  adx="true";  rr=1.5 },
    [ordered]@{ name="C5_all_ON_RR1.0";     quality="true";  momentum="true";  adx="true";  rr=1.0 },
    [ordered]@{ name="C6_all_ON_RR2.0";     quality="true";  momentum="true";  adx="true";  rr=2.0 },
    [ordered]@{ name="C7_all_ON_RR0.7";     quality="true";  momentum="true";  adx="true";  rr=0.7 }
)

$results = @()

foreach ($cfg in $configs) {
    Write-Host "[$($cfg.name)] ..." -ForegroundColor Cyan

    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PullbackTrend""`r`nsymbol:    ""$symbol""`r`nperiod:    ""$period""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  TrendMA_Period:          200`r`n  FastEMA_Period:          20`r`n  SlowEMA_Period:          50`r`n  RequireBullishCandle:    true`r`n  UsePullbackQuality:      $($cfg.quality)`r`n  UseMomentumConfirm:      $($cfg.momentum)`r`n  UseADXFilter:            $($cfg.adx)`r`n  ADX_Period:              14`r`n  ADX_Threshold:           25.0`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             1.5`r`n  RR_Ratio:                $($cfg.rr)`r`n  StopLoss_Pips:           30`r`n  TakeProfit_Pips:         45`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260622`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""PBH4_$($cfg.name)""`r`n"

    [System.IO.File]::WriteAllText(
        "C:\Users\f\source\repos\mt5_backtester\configs\pb_compare_h4_tmp.yaml",
        $yaml,
        [System.Text.Encoding]::UTF8
    )

    & $mt5bt run configs\pb_compare_h4_tmp.yaml --no-charts 2>&1 | Out-Null

    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($csvFile -and (Test-Path $csvFile.FullName)) {
        $data = @{}
        Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
            $parts = $_ -split ','
            if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
        }
        $netProfit   = [double]$data["net_profit"]
        $grossProfit = [double]$data["gross_profit"]
        $grossLoss   = [math]::Abs([double]$data["gross_loss"])
        $trades      = [int]$data["total_trades"]
        $wt          = [double]$data["win_trades"]
        $lt          = [double]$data["loss_trades"]
        $pf          = [double]$data["profit_factor"]

        $winRate  = if (($wt + $lt) -gt 0) { [math]::Round($wt / ($wt + $lt) * 100, 1) } else { 0 }
        $avgWin   = if ($wt -gt 0) { $grossProfit / $wt } else { 0 }
        $avgLoss  = if ($lt -gt 0) { $grossLoss / $lt } else { 0 }
        $effRR    = if ($avgLoss -gt 0) { [math]::Round($avgWin / $avgLoss, 2) } else { 0 }
        $wr       = $winRate / 100.0
        $expR     = [math]::Round($wr * $effRR - (1 - $wr), 3)

        $results += [PSCustomObject]@{
            Config = $cfg.name; Net = $netProfit; WinRate = $winRate
            EffRR = $effRR; ExpR = $expR; PF = $pf; Trades = $trades
        }

        $sign  = if ($netProfit -ge 0) { "+" } else { "" }
        $color = if ($netProfit -ge 0) { "Green" } else { "Red" }
        Write-Host ("  -> {0}{1:N0} JPY | WinRate {2}% | EffRR {3} | ExpR {4} | PF {5} | {6} trades" -f $sign, $netProfit, $winRate, $effRR, $expR, $pf, $trades) -ForegroundColor $color
    } else {
        Write-Host "  -> CSV not found" -ForegroundColor Yellow
    }
}

function Format-Profit($v) {
    $sign = if ($v -ge 0) { "+" } else { "" }
    return ("{0}{1:N0}" -f $sign, $v)
}

Write-Host ""
Write-Host "===== PullbackTrend v1.1 compare (USDJPY H4, 2021.06-2026.06) =====" -ForegroundColor Yellow
Write-Host "Target: WinRate 60% / EffRR 1.5 / ExpR +0.5" -ForegroundColor Yellow
Write-Host ("{0,-22} {1,10} {2,9} {3,7} {4,7} {5,6} {6,7}" -f "Config","Net","WinRate","EffRR","ExpR","PF","Trades")
Write-Host ("-" * 76)
foreach ($r in $results) {
    $color = if ($r.WinRate -ge 55) { "Green" } elseif ($r.WinRate -ge 48) { "White" } else { "Gray" }
    Write-Host ("{0,-22} {1,10} {2,8}% {3,7} {4,7} {5,6} {6,7}" -f $r.Config, (Format-Profit $r.Net), $r.WinRate, $r.EffRR, $r.ExpR, $r.PF, $r.Trades) -ForegroundColor $color
}
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
