# PullbackTrend パラメータ最適化 — USDJPY H4 単独（過去5年フル）
# ADX_Threshold / ATR_SL_Mult / RR_Ratio を個別スイープ
# 基準: ADX=25, ATR_SL=1.5, RR=2.0

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pb_opt_result.csv"

$fromDate = "2021.06.21"
$toDate   = "2026.06.20"

function Run-Backtest($adx, $atrSL, $rr) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PullbackTrend""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  TrendMA_Period:          200`r`n  FastEMA_Period:          20`r`n  SlowEMA_Period:          50`r`n  RequireBullishCandle:    true`r`n  UsePullbackQuality:      true`r`n  UseMomentumConfirm:      true`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           $adx`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             $atrSL`r`n  RR_Ratio:                $rr`r`n  StopLoss_Pips:           30`r`n  TakeProfit_Pips:         45`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260622`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""PB_opt""`r`n"

    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pb_opt_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pb_opt_tmp.yaml --no-charts 2>&1 | Out-Null

    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return $null }

    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    $net    = [double]$data["net_profit"]
    $gp     = [double]$data["gross_profit"]
    $gl     = [math]::Abs([double]$data["gross_loss"])
    $trades = [int]$data["total_trades"]
    $wt     = [double]$data["win_trades"]
    $lt     = [double]$data["loss_trades"]
    $pf     = [double]$data["profit_factor"]
    $wr     = if (($wt+$lt) -gt 0) { [math]::Round($wt/($wt+$lt)*100,1) } else { 0 }
    $aw     = if ($wt -gt 0) { $gp/$wt } else { 0 }
    $al     = if ($lt -gt 0) { $gl/$lt } else { 0 }
    $eff    = if ($al -gt 0) { [math]::Round($aw/$al,2) } else { 0 }
    $expR   = [math]::Round(($wr/100.0)*$eff - (1-$wr/100.0), 3)

    return [PSCustomObject]@{ Net=$net; WinRate=$wr; EffRR=$eff; ExpR=$expR; PF=$pf; Trades=$trades }
}

function Format-Profit($v) {
    $sign = if ($v -ge 0) { "+" } else { "" }
    return ("{0}{1:N0}" -f $sign, $v)
}

function Show-Result($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-10} -> CSV not found" -f $label) -ForegroundColor Yellow; return }
    $color = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-12} Net {1,9} | Win {2,5}% | EffRR {3,5} | ExpR {4,7} | PF {5,6} | {6,4} trades" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.EffRR, $r.ExpR, $r.PF, $r.Trades) -ForegroundColor $color
}

# === スイープ1: ADX_Threshold (ATR_SL=1.5, RR=2.0固定) ===
Write-Host ""
Write-Host "=== Sweep 1: ADX_Threshold (ATR_SL=1.5, RR=2.0) ===" -ForegroundColor Cyan
$adxList = @(20.0, 22.5, 25.0, 27.5, 30.0)
$adxResults = @{}
foreach ($adx in $adxList) {
    $r = Run-Backtest $adx 1.5 2.0
    $adxResults[$adx] = $r
    Show-Result ("ADX=$adx") $r
}
$bestAdx = ($adxResults.GetEnumerator() | Sort-Object { $_.Value.Net } -Descending | Select-Object -First 1).Key
Write-Host ("  >> Best ADX = $bestAdx") -ForegroundColor Magenta

# === スイープ2: ATR_SL_Mult (ADX=best, RR=2.0固定) ===
Write-Host ""
Write-Host "=== Sweep 2: ATR_SL_Mult (ADX=$bestAdx, RR=2.0) ===" -ForegroundColor Cyan
$atrList = @(1.0, 1.25, 1.5, 2.0, 2.5)
$atrResults = @{}
foreach ($atrSL in $atrList) {
    $r = Run-Backtest $bestAdx $atrSL 2.0
    $atrResults[$atrSL] = $r
    Show-Result ("ATR_SL=$atrSL") $r
}
$bestAtr = ($atrResults.GetEnumerator() | Sort-Object { $_.Value.Net } -Descending | Select-Object -First 1).Key
Write-Host ("  >> Best ATR_SL = $bestAtr") -ForegroundColor Magenta

# === スイープ3: RR_Ratio (ADX=best, ATR_SL=best固定) ===
Write-Host ""
Write-Host "=== Sweep 3: RR_Ratio (ADX=$bestAdx, ATR_SL=$bestAtr) ===" -ForegroundColor Cyan
$rrList = @(1.5, 2.0, 2.5, 3.0)
$rrResults = @{}
foreach ($rr in $rrList) {
    $r = Run-Backtest $bestAdx $bestAtr $rr
    $rrResults[$rr] = $r
    Show-Result ("RR=$rr") $r
}
$bestRr = ($rrResults.GetEnumerator() | Sort-Object { $_.Value.Net } -Descending | Select-Object -First 1).Key
Write-Host ("  >> Best RR = $bestRr") -ForegroundColor Magenta

# === 最終ベスト構成 ===
Write-Host ""
Write-Host "===== OPTIMIZED CONFIG (USDJPY H4, 2021.06-2026.06) =====" -ForegroundColor Yellow
$final = Run-Backtest $bestAdx $bestAtr $bestRr
Write-Host ("  ADX_Threshold = $bestAdx | ATR_SL_Mult = $bestAtr | RR_Ratio = $bestRr") -ForegroundColor White
Show-Result "FINAL" $final
Write-Host ""
Write-Host ("  Baseline (ADX25/ATR1.5/RR2.0): +24,856 JPY / Win 39.7% / EffRR 1.85") -ForegroundColor Gray
Write-Host "Done!" -ForegroundColor Green
