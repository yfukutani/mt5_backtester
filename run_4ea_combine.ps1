# 4-EA portfolio check: PB + RSI + Keltner + DMI
# Does adding Keltner/DMI (trend-follow, no env filter) improve the portfolio?
# Keltner/DMI yearly (USDJPY H4, best 5yr config) over full 2016-2026.

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"

# Known yearly (robust EAs):
$pb  = @{ 2016=20699; 2017=-7791; 2018=-7543; 2019=-4939; 2020=-906; 2021=3928; 2022=18081; 2023=2674; 2024=7354; 2025=-4182; 2026=-1036 }
$rsi = @{ 2016=-1261; 2017=4687; 2018=-8484; 2019=11486; 2020=-2023; 2021=-10825; 2022=2737; 2023=4502; 2024=11313; 2025=553; 2026=-951 }

function Run-Keltner($from, $to) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""KeltnerBreakout""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  EMA_Period:              20`r`n  ATR_Period:              14`r`n  ChannelMult:             1.5`r`n  UseRetest:               false`r`n  Retest_Timeout_Bars:     10`r`n  TrendMA_Period:          200`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           22.5`r`n  UseATRStops:             true`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           40`r`n  TakeProfit_Pips:         80`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260625`r`n  ResultFileName:          ""c4_kelt.csv""`r`nreport_dir:  ""results""`r`nreport_name: ""c4_kelt""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\c4_kelt_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\c4_kelt_tmp.yaml --no-charts 2>&1 | Out-Null
    $f = Get-ChildItem $testerRoot -Recurse -Filter "c4_kelt.csv" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($f -and (Test-Path $f.FullName))) { return 0 }
    $d=@{}; Get-Content $f.FullName | Select-Object -Skip 1 | ForEach-Object { $p=$_ -split ','; if($p.Count -ge 2){$d[$p[0].Trim()]=$p[1].Trim()} }
    return [double]$d["net_profit"]
}

function Run-DMI($from, $to) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""DMI_Cross""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  ADX_Period:              14`r`n  ADX_Threshold:           25.0`r`n  UseADXSlope:             false`r`n  UseDISpread:             false`r`n  DI_Min_Spread:           3.0`r`n  TrendMA_Period:          200`r`n  UseMAFilter:             true`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           40`r`n  TakeProfit_Pips:         80`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260626`r`n  ResultFileName:          ""c4_dmi.csv""`r`nreport_dir:  ""results""`r`nreport_name: ""c4_dmi""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\c4_dmi_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\c4_dmi_tmp.yaml --no-charts 2>&1 | Out-Null
    $f = Get-ChildItem $testerRoot -Recurse -Filter "c4_dmi.csv" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($f -and (Test-Path $f.FullName))) { return 0 }
    $d=@{}; Get-Content $f.FullName | Select-Object -Skip 1 | ForEach-Object { $p=$_ -split ','; if($p.Count -ge 2){$d[$p[0].Trim()]=$p[1].Trim()} }
    return [double]$d["net_profit"]
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }
function Corr($a, $b) {
    $n=$a.Count; $mA=($a|Measure-Object -Average).Average; $mB=($b|Measure-Object -Average).Average
    $cov=0;$vA=0;$vB=0
    for($i=0;$i -lt $n;$i++){ $dA=$a[$i]-$mA; $dB=$b[$i]-$mB; $cov+=$dA*$dB; $vA+=$dA*$dA; $vB+=$dB*$dB }
    if ($vA -gt 0 -and $vB -gt 0) { return [math]::Round($cov/[math]::Sqrt($vA*$vB),3) } else { return 0 }
}

$years = 2016..2026
$kelt = @{}; $dmi = @{}

Write-Host ""
Write-Host "=== Keltner & DMI yearly (USDJPY H4, full period) ===" -ForegroundColor Cyan
foreach ($y in $years) {
    $from = "$y.01.01"; $to = if ($y -eq 2026) { "2026.06.20" } else { "$y.12.31" }
    $kelt[$y] = Run-Keltner $from $to
    $dmi[$y]  = Run-DMI $from $to
    Write-Host ("  $y  Kelt: {0,9}  DMI: {1,9}" -f (Format-Profit $kelt[$y]), (Format-Profit $dmi[$y]))
}

Write-Host ""
Write-Host "=== Yearly all 4 EAs + combined ===" -ForegroundColor Yellow
Write-Host ("{0,-6} {1,9} {2,9} {3,9} {4,9} {5,10}" -f "Year","PB","RSI","Kelt","DMI","4EA-Sum")
Write-Host ("-" * 56)
$pbA=@();$rsiA=@();$keA=@();$dmA=@()
$sumPB=0;$sumRSI=0;$sumKE=0;$sumDM=0;$sum4=0
$sum2=0  # PB+RSI only
foreach ($y in $years) {
    $p=[double]$pb[$y]; $r=[double]$rsi[$y]; $k=[double]$kelt[$y]; $d=[double]$dmi[$y]
    $s4=$p+$r+$k+$d
    $pbA+=$p;$rsiA+=$r;$keA+=$k;$dmA+=$d
    $sumPB+=$p;$sumRSI+=$r;$sumKE+=$k;$sumDM+=$d;$sum4+=$s4;$sum2+=($p+$r)
    $col = if ($s4 -ge 0) { "Green" } else { "Red" }
    Write-Host ("{0,-6} {1,9} {2,9} {3,9} {4,9} {5,10}" -f $y,(Format-Profit $p),(Format-Profit $r),(Format-Profit $k),(Format-Profit $d),(Format-Profit $s4)) -ForegroundColor $col
}
Write-Host ("-" * 56)
Write-Host ("{0,-6} {1,9} {2,9} {3,9} {4,9} {5,10}" -f "SUM",(Format-Profit $sumPB),(Format-Profit $sumRSI),(Format-Profit $sumKE),(Format-Profit $sumDM),(Format-Profit $sum4))

Write-Host ""
Write-Host "=== Analysis ===" -ForegroundColor Yellow
Write-Host ("  Totals: PB {0} | RSI {1} | Kelt {2} | DMI {3}" -f (Format-Profit $sumPB),(Format-Profit $sumRSI),(Format-Profit $sumKE),(Format-Profit $sumDM))
Write-Host ("  PB+RSI (current best): {0}" -f (Format-Profit $sum2))
Write-Host ("  PB+RSI+Kelt+DMI (4EA): {0}" -f (Format-Profit $sum4))
Write-Host ""
Write-Host ("  Correlation Kelt vs PB: {0}  (high = redundant with trend EA)" -f (Corr $keA $pbA))
Write-Host ("  Correlation DMI  vs PB: {0}" -f (Corr $dmA $pbA))
Write-Host ("  Correlation Kelt vs RSI: {0}" -f (Corr $keA $rsiA))
Write-Host ("  Correlation DMI  vs RSI: {0}" -f (Corr $dmA $rsiA))
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
