# FINAL: robust RSI_Reversal + robust PullbackTrend - complementary check
# RSI robust = USDJPY H4 (range<=0.2) + EURUSD H1 (range<=0.2)
# PB = JPY-cross 3 symbols (env filter)
# Yearly 2016-2026, correlation analysis.

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "final_eu.csv"

# Known yearly (from prior runs):
# USDJPY H4 RSI range<=0.2 (reopt2)
$usdjpyH4 = @{ 2016=2241; 2017=3580; 2018=802; 2019=4168; 2020=870; 2021=-9474; 2022=1254; 2023=-954; 2024=3224; 2025=-442; 2026=1604 }
# PullbackTrend JPY-cross 3 symbols (run_combined_portfolio)
$pb = @{ 2016=20699; 2017=-7791; 2018=-7543; 2019=-4939; 2020=-906; 2021=3928; 2022=18081; 2023=2674; 2024=7354; 2025=-4182; 2026=-1036 }

function Run-EURUSD-H1($from, $to) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""RSI_Reversal""`r`nsymbol:    ""EURUSD""`r`nperiod:    ""H1""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  MA_Period:               200`r`n  BB_Period:               20`r`n  BB_Deviation:            2.5`r`n  RSI_Period:              14`r`n  RSI_OverboughtExtreme:   75.0`r`n  RSI_Overbought:          72.5`r`n  RSI_OversoldExtreme:     27.5`r`n  RSI_Oversold:            30.0`r`n  UseDoublePattern:        false`r`n  Swing_Lookback:          3`r`n  DP_Pattern_Bars:         60`r`n  DP_Tolerance_ATR:        0.5`r`n  UseRangeFilter:          true`r`n  Range_Slope_Lookback:    20`r`n  Range_Slope_Max_ATR:     0.2`r`n  UseTrailingStop:         false`r`n  UseBreakeven:            false`r`n  UseVolatilityFilter:     false`r`n  UseATRStopLoss:          false`r`n  UseADXFilter:            false`r`n  UseTimeFilter:           false`r`n  LotSize:                 0.01`r`n  StopLoss_Pips:           45`r`n  TakeProfit_Pips:         105`r`n  MagicNumber:             20260605`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""final_eu""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\final_eu_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\final_eu_tmp.yaml --no-charts 2>&1 | Out-Null
    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return 0 }
    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    return [double]$data["net_profit"]
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }

$years = 2016..2026

Write-Host ""
Write-Host "=== Computing EURUSD H1 (range<=0.2) yearly ===" -ForegroundColor Cyan
$eu = @{}
foreach ($y in $years) {
    $from = "$y.01.01"; $to = if ($y -eq 2026) { "2026.06.20" } else { "$y.12.31" }
    $eu[$y] = Run-EURUSD-H1 $from $to
    Write-Host ("  $y EURUSD: {0}" -f (Format-Profit $eu[$y]))
}

Write-Host ""
Write-Host "=== FINAL: robust RSI (reversal) + robust PB (trend) ===" -ForegroundColor Yellow
Write-Host ("{0,-6} {1,11} {2,11} {3,11}" -f "Year","RSI(robust)","PB(trend)","Combined")
Write-Host ("-" * 42)
$rsiArr=@(); $pbArr=@(); $sumR=0; $sumP=0; $sumC=0
foreach ($y in $years) {
    $r = [double]$usdjpyH4[$y] + [double]$eu[$y]
    $p = [double]$pb[$y]
    $c = $r + $p
    $rsiArr += $r; $pbArr += $p
    $sumR += $r; $sumP += $p; $sumC += $c
    $col = if ($c -ge 0) { "Green" } else { "Red" }
    Write-Host ("{0,-6} {1,11} {2,11} {3,11}" -f $y, (Format-Profit $r), (Format-Profit $p), (Format-Profit $c)) -ForegroundColor $col
}
Write-Host ("-" * 42)
Write-Host ("{0,-6} {1,11} {2,11} {3,11}" -f "SUM", (Format-Profit $sumR), (Format-Profit $sumP), (Format-Profit $sumC))

# correlation
$n=$rsiArr.Count; $mR=($rsiArr|Measure-Object -Average).Average; $mP=($pbArr|Measure-Object -Average).Average
$cov=0;$vR=0;$vP=0
for($i=0;$i -lt $n;$i++){ $dR=$rsiArr[$i]-$mR; $dP=$pbArr[$i]-$mP; $cov+=$dR*$dP; $vR+=$dR*$dR; $vP+=$dP*$dP }
$corr = if ($vR -gt 0 -and $vP -gt 0) { [math]::Round($cov/[math]::Sqrt($vR*$vP),3) } else { 0 }
$rPos=($rsiArr|Where-Object{$_ -ge 0}).Count; $pPos=($pbArr|Where-Object{$_ -ge 0}).Count
$cArr = for($i=0;$i -lt $n;$i++){ $rsiArr[$i]+$pbArr[$i] }
$cPos=($cArr|Where-Object{$_ -ge 0}).Count

Write-Host ""
Write-Host "=== Analysis ===" -ForegroundColor Yellow
Write-Host ("  Correlation (RSI robust vs PB): {0}  (prev overfit RSI was +0.398)" -f $corr)
Write-Host ("  Profitable years: RSI {0}/11 | PB {1}/11 | Combined {2}/11" -f $rPos, $pPos, $cPos)
Write-Host ("  Total: RSI {0} | PB {1} | Combined {2}" -f (Format-Profit $sumR), (Format-Profit $sumP), (Format-Profit $sumC))
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
