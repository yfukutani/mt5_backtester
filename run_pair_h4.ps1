# PairTrade EUR/GBP H4 raw 1:1 - is a higher timeframe more robust / lower cost?
# H4 LB ~50 bars ~= H1 LB200. Test param sensitivity (spike vs plateau).

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "pair_h4_result.csv"

function Run-Pair($entryZ, $exitZ, $lookback, $stopZ) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""PairTrade""`r`nsymbol:    ""EURUSD""`r`nperiod:    ""H4""`r`nfrom_date: ""2016.06.21""`r`nto_date:   ""2026.06.20""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  SecondSymbol:    ""GBPUSD""`r`n  Lookback:        $lookback`r`n  UseLogSpread:    0`r`n  UseBetaHedge:    0`r`n  Entry_Z:         $entryZ`r`n  Exit_Z:          $exitZ`r`n  Stop_Z:          $stopZ`r`n  LotSize:         0.01`r`n  MagicNumber:     20260629`r`n  ResultFileName:  ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""pair_h4""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\pair_h4_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\pair_h4_tmp.yaml --no-charts 2>&1 | Out-Null
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
Write-Host "=== EUR/GBP H4 raw 1:1, Entry_Z sensitivity (Exit0 LB50 Stop5) ===" -ForegroundColor Cyan
foreach ($e in @(2.0, 2.5, 3.0, 3.5)) { Show "Entry=$e" (Run-Pair $e 0.0 50 5.0) }
Write-Host ""
Write-Host "=== Lookback sensitivity (Entry2.5 Exit0 Stop5) ===" -ForegroundColor Cyan
foreach ($l in @(30, 50, 75, 100)) { Show "LB=$l" (Run-Pair 2.5 0.0 $l 5.0) }
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
