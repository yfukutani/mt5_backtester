# PairTrade final: best config yearly (full period) + correlation with PB/RSI
# Best: Entry4.0 Exit0.0 LB200 Stop5.0 (EURUSD/GBPUSD H1)

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pair_final_result.csv"

$pb  = @{ 2016=20699; 2017=-7791; 2018=-7543; 2019=-4939; 2020=-906; 2021=3928; 2022=18081; 2023=2674; 2024=7354; 2025=-4182; 2026=-1036 }
$rsi = @{ 2016=-1261; 2017=4687; 2018=-8484; 2019=11486; 2020=-2023; 2021=-10825; 2022=2737; 2023=4502; 2024=11313; 2025=553; 2026=-951 }

function Run-Pair($from, $to) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PairTrade""`r`nsymbol:    ""EURUSD""`r`nperiod:    ""H1""`r`nfrom_date: ""$from""`r`nto_date:   ""$to""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  SecondSymbol:    ""GBPUSD""`r`n  Lookback:        200`r`n  Entry_Z:         4.0`r`n  Exit_Z:          0.0`r`n  Stop_Z:          5.0`r`n  LotSize:         0.01`r`n  MagicNumber:     20260629`r`n  ResultFileName:  ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""pair_final""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pair_final_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pair_final_tmp.yaml --no-charts 2>&1 | Out-Null
    $f = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
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
$pair = @{}

Write-Host ""
Write-Host "=== PairTrade yearly (E4.0 Exit0 LB200 Stop5, full period) ===" -ForegroundColor Cyan
foreach ($y in $years) {
    $from = "$y.01.01"; $to = if ($y -eq 2026) { "2026.06.20" } else { "$y.12.31" }
    $pair[$y] = Run-Pair $from $to
    Write-Host ("  $y Pair: {0}" -f (Format-Profit $pair[$y]))
}

Write-Host ""
Write-Host "=== 3-EA portfolio: PB + RSI + Pair ===" -ForegroundColor Yellow
Write-Host ("{0,-6} {1,9} {2,9} {3,9} {4,10}" -f "Year","PB","RSI","Pair","3EA-Sum")
Write-Host ("-" * 48)
$pbA=@();$rsiA=@();$paA=@();$prA=@()
$sumPB=0;$sumRSI=0;$sumPA=0;$sum2=0;$sum3=0
foreach ($y in $years) {
    $p=[double]$pb[$y]; $r=[double]$rsi[$y]; $a=[double]$pair[$y]
    $s2=$p+$r; $s3=$p+$r+$a
    $pbA+=$p;$rsiA+=$r;$paA+=$a;$prA+=$s2
    $sumPB+=$p;$sumRSI+=$r;$sumPA+=$a;$sum2+=$s2;$sum3+=$s3
    $col = if ($s3 -ge 0) { "Green" } else { "Red" }
    Write-Host ("{0,-6} {1,9} {2,9} {3,9} {4,10}" -f $y,(Format-Profit $p),(Format-Profit $r),(Format-Profit $a),(Format-Profit $s3)) -ForegroundColor $col
}
Write-Host ("-" * 48)
Write-Host ("{0,-6} {1,9} {2,9} {3,9} {4,10}" -f "SUM",(Format-Profit $sumPB),(Format-Profit $sumRSI),(Format-Profit $sumPA),(Format-Profit $sum3))

Write-Host ""
Write-Host "=== Analysis ===" -ForegroundColor Yellow
Write-Host ("  Pair total: {0}" -f (Format-Profit $sumPA))
Write-Host ("  PB+RSI (2EA): {0} | PB+RSI+Pair (3EA): {1}" -f (Format-Profit $sum2), (Format-Profit $sum3))
Write-Host ("  Correlation Pair vs PB:  {0}" -f (Corr $paA $pbA))
Write-Host ("  Correlation Pair vs RSI: {0}" -f (Corr $paA $rsiA))
Write-Host ("  Correlation Pair vs (PB+RSI): {0}" -f (Corr $paA $prA))
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
