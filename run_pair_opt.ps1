# PairTrade parameter sweep - EURUSD/GBPUSD H1, 2021-2026
# 50% win + PF0.9 = cost bleed. Widen entry/exit to cut trades & gain edge.

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pair_opt_result.csv"

function Run-Pair($entryZ, $exitZ, $lookback) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PairTrade""`r`nsymbol:    ""EURUSD""`r`nperiod:    ""H1""`r`nfrom_date: ""2021.06.21""`r`nto_date:   ""2026.06.20""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  SecondSymbol:    ""GBPUSD""`r`n  Lookback:        $lookback`r`n  Entry_Z:         $entryZ`r`n  Exit_Z:          $exitZ`r`n  Stop_Z:          4.0`r`n  LotSize:         0.01`r`n  MagicNumber:     20260629`r`n  ResultFileName:  ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""pair_opt""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pair_opt_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pair_opt_tmp.yaml --no-charts 2>&1 | Out-Null
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
    if ($null -eq $r) { Write-Host ("  {0,-18} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-18} Net {1,9} | Win {2,5}% | PF {3,6} | DD {4,5:N1}% | {5,5} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.PF, $r.DD, $r.Trades) -ForegroundColor $c
}

Write-Host ""
Write-Host "=== Sweep 1: Entry_Z (Exit0.5, LB100) ===" -ForegroundColor Cyan
foreach ($e in @(2.0, 2.5, 3.0, 3.5)) { Show ("Entry=$e") (Run-Pair $e 0.5 100) }

Write-Host ""
Write-Host "=== Sweep 2: Exit_Z (Entry3.0, LB100) ===" -ForegroundColor Cyan
foreach ($x in @(0.0, 0.5, 1.0)) { Show ("Exit=$x") (Run-Pair 3.0 $x 100) }

Write-Host ""
Write-Host "=== Sweep 3: Lookback (Entry3.0, Exit0.0) ===" -ForegroundColor Cyan
foreach ($l in @(50, 100, 200)) { Show ("LB=$l") (Run-Pair 3.0 0.0 $l) }

Write-Host ""
Write-Host "Question: any config profitable? (pair trade is cost-sensitive)" -ForegroundColor Yellow
Write-Host "Done!" -ForegroundColor Green
