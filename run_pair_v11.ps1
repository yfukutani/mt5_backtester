# PairTrade v1.1 A/B test: log-spread + beta-hedge
# Baseline (both off) must reproduce v1.0 +6,694 on EUR/GBP full period.
# Then test log, beta, log+beta. Also EUR/CHF (inverse pair) with beta.

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pair_v11_result.csv"

function Run-Pair($mainSym, $second, $useLog, $useBeta, $entryZ, $exitZ, $lookback, $stopZ) {
    $lg = if ($useLog)  { 1 } else { 0 }
    $bt = if ($useBeta) { 1 } else { 0 }
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PairTrade""`r`nsymbol:    ""$mainSym""`r`nperiod:    ""H1""`r`nfrom_date: ""2016.06.21""`r`nto_date:   ""2026.06.20""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  SecondSymbol:    ""$second""`r`n  Lookback:        $lookback`r`n  UseLogSpread:    $lg`r`n  UseBetaHedge:    $bt`r`n  Entry_Z:         $entryZ`r`n  Exit_Z:          $exitZ`r`n  Stop_Z:          $stopZ`r`n  LotSize:         0.01`r`n  MagicNumber:     20260629`r`n  ResultFileName:  ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""pair_v11""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pair_v11_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pair_v11_tmp.yaml --no-charts 2>&1 | Out-Null
    $f = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($f -and (Test-Path $f.FullName))) { return $null }
    $d=@{}; Get-Content $f.FullName | Select-Object -Skip 1 | ForEach-Object { $p=$_ -split ','; if($p.Count -ge 2){$d[$p[0].Trim()]=$p[1].Trim()} }
    $net=[double]$d["net_profit"]; $wt=[double]$d["win_trades"]; $lt=[double]$d["loss_trades"]
    $tr=[int]$d["total_trades"]; $pf=[double]$d["profit_factor"]; $dd=[double]$d["max_dd_pct"]
    $wr = if (($wt+$lt) -gt 0) { [math]::Round($wt/($wt+$lt)*100,1) } else { 0 }
    return [PSCustomObject]@{ Net=$net; WinRate=$wr; PF=$pf; DD=$dd; Trades=$tr }
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }
function Show($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-26} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-26} Net {1,9} | Win {2,5}% | PF {3,6} | DD {4,5:N1}% | {5,5} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.PF, $r.DD, $r.Trades) -ForegroundColor $c
}

# Optimal z-params from v1.0: E4.0 Exit0.0 LB200 Stop5.0
Write-Host ""
Write-Host "=== EUR/GBP full period (2016-2026), z=E4.0/Ex0.0/LB200/St5 ===" -ForegroundColor Cyan
Show "v1.0 baseline (raw,1:1)"  (Run-Pair "EURUSD" "GBPUSD" $false $false 4.0 0.0 200 5.0)
Show "+log only"                (Run-Pair "EURUSD" "GBPUSD" $true  $false 4.0 0.0 200 5.0)
Show "+beta only"               (Run-Pair "EURUSD" "GBPUSD" $false $true  4.0 0.0 200 5.0)
Show "+log+beta"                (Run-Pair "EURUSD" "GBPUSD" $true  $true  4.0 0.0 200 5.0)

Write-Host ""
Write-Host "=== EUR/CHF inverse pair (beta auto-handles sign) ===" -ForegroundColor Cyan
Show "EUR/CHF +log+beta"        (Run-Pair "EURUSD" "USDCHF" $true  $true  4.0 0.0 200 5.0)
Show "EUR/CHF +beta only"       (Run-Pair "EURUSD" "USDCHF" $false $true  4.0 0.0 200 5.0)

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
