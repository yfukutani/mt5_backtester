# KeltnerBreakout 構成比較 — USDJPY H4（過去5年 2021.06.21-2026.06.20）
# ChannelMult / RR / ADX有無 をスイープ。PullbackTrend(+43,341円)と比較

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "kelt_compare_result.csv"

$fromDate = "2021.06.21"
$toDate   = "2026.06.20"

function Run-Backtest($chMult, $rr, $adx) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""KeltnerBreakout""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  EMA_Period:              20`r`n  ATR_Period:              14`r`n  ChannelMult:             $chMult`r`n  TrendMA_Period:          200`r`n  UseADXFilter:            $adx`r`n  ADX_Period:              14`r`n  ADX_Threshold:           22.5`r`n  UseATRStops:             true`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                $rr`r`n  StopLoss_Pips:           40`r`n  TakeProfit_Pips:         80`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260625`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""Kelt_compare""`r`n"

    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\kelt_compare_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\kelt_compare_tmp.yaml --no-charts 2>&1 | Out-Null

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
    $expR   = if (($wt+$lt) -gt 0) { [math]::Round(($wr/100.0)*$eff - (1-$wr/100.0), 3) } else { 0 }

    return [PSCustomObject]@{ Net=$net; WinRate=$wr; EffRR=$eff; ExpR=$expR; PF=$pf; Trades=$trades }
}

function Format-Profit($v) {
    $sign = if ($v -ge 0) { "+" } else { "" }
    return ("{0}{1:N0}" -f $sign, $v)
}

function Show-Result($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-22} -> CSV not found" -f $label) -ForegroundColor Yellow; return }
    $color = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-22} Net {1,9} | Win {2,5}% | EffRR {3,5} | ExpR {4,7} | PF {5,6} | {6,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.EffRR, $r.ExpR, $r.PF, $r.Trades) -ForegroundColor $color
}

# === スイープ1: ChannelMult (RR=2.0, ADX=ON) ===
Write-Host ""
Write-Host "=== Sweep 1: ChannelMult (RR=2.0, ADX ON) ===" -ForegroundColor Cyan
$chList = @(1.5, 2.0, 2.5, 3.0)
$chResults = @{}
foreach ($ch in $chList) {
    $r = Run-Backtest $ch 2.0 "true"
    $chResults[$ch] = $r
    Show-Result ("ChMult=$ch") $r
}
$bestCh = ($chResults.GetEnumerator() | Sort-Object { $_.Value.Net } -Descending | Select-Object -First 1).Key
Write-Host ("  >> Best ChannelMult = $bestCh") -ForegroundColor Magenta

# === スイープ2: RR_Ratio (ChMult=best, ADX=ON) ===
Write-Host ""
Write-Host "=== Sweep 2: RR_Ratio (ChMult=$bestCh, ADX ON) ===" -ForegroundColor Cyan
$rrList = @(1.5, 2.0, 2.5, 3.0)
$rrResults = @{}
foreach ($rr in $rrList) {
    $r = Run-Backtest $bestCh $rr "true"
    $rrResults[$rr] = $r
    Show-Result ("RR=$rr") $r
}
$bestRr = ($rrResults.GetEnumerator() | Sort-Object { $_.Value.Net } -Descending | Select-Object -First 1).Key
Write-Host ("  >> Best RR = $bestRr") -ForegroundColor Magenta

# === スイープ3: ADX有無 (ChMult=best, RR=best) ===
Write-Host ""
Write-Host "=== Sweep 3: ADX ON/OFF (ChMult=$bestCh, RR=$bestRr) ===" -ForegroundColor Cyan
$rOn  = Run-Backtest $bestCh $bestRr "true"
$rOff = Run-Backtest $bestCh $bestRr "false"
Show-Result "ADX=ON"  $rOn
Show-Result "ADX=OFF" $rOff

# === 最終 ===
Write-Host ""
Write-Host "===== KeltnerBreakout BEST (USDJPY H4, 2021.06-2026.06) =====" -ForegroundColor Yellow
$bestAdx = if ($rOff.Net -gt $rOn.Net) { "false" } else { "true" }
$final = Run-Backtest $bestCh $bestRr $bestAdx
Write-Host ("  ChannelMult=$bestCh | RR=$bestRr | ADX=$bestAdx") -ForegroundColor White
Show-Result "FINAL" $final
Write-Host ""
Write-Host "  [比較] PullbackTrend BEST: +43,341 JPY / Win 44.2% / EffRR 1.81 / PF 1.44" -ForegroundColor Gray
Write-Host "Done!" -ForegroundColor Green
