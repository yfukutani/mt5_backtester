# DMI_Cross 品質フィルター強度チューニング — USDJPY H4（過去5年）
# ADX傾き・DI乖離を個別/組み合わせ、乖離幅を緩めて最適点を探る

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"
$csvName    = "dmi_tune_result.csv"

$fromDate = "2021.06.21"
$toDate   = "2026.06.20"

function Run-DMI($slope, $spread, $min) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""DMI_Cross""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  ADX_Period:              14`r`n  ADX_Threshold:           25.0`r`n  UseADXSlope:             $slope`r`n  UseDISpread:             $spread`r`n  DI_Min_Spread:           $min`r`n  TrendMA_Period:          200`r`n  UseMAFilter:             true`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           40`r`n  TakeProfit_Pips:         80`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260626`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""DMI_tune""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\dmi_tune_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\dmi_tune_tmp.yaml --no-charts 2>&1 | Out-Null

    $csvFile = Get-ChildItem $testerRoot -Recurse -Filter $csvName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not ($csvFile -and (Test-Path $csvFile.FullName))) { return $null }
    $data = @{}
    Get-Content $csvFile.FullName | Select-Object -Skip 1 | ForEach-Object {
        $parts = $_ -split ','
        if ($parts.Count -ge 2) { $data[$parts[0].Trim()] = $parts[1].Trim() }
    }
    $net=[double]$data["net_profit"]; $gp=[double]$data["gross_profit"]; $gl=[math]::Abs([double]$data["gross_loss"])
    $wt=[double]$data["win_trades"]; $lt=[double]$data["loss_trades"]; $tr=[int]$data["total_trades"]; $pf=[double]$data["profit_factor"]
    $wr = if (($wt+$lt) -gt 0) { [math]::Round($wt/($wt+$lt)*100,1) } else { 0 }
    $aw = if ($wt -gt 0) { $gp/$wt } else { 0 }
    $al = if ($lt -gt 0) { $gl/$lt } else { 0 }
    $eff = if ($al -gt 0) { [math]::Round($aw/$al,2) } else { 0 }
    return [PSCustomObject]@{ Net=$net; WinRate=$wr; EffRR=$eff; PF=$pf; Trades=$tr }
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }
function Show($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-24} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Trades -lt 20) { "DarkGray" } elseif ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-24} Net {1,9} | Win {2,5}% | EffRR {3,5} | PF {4,6} | {5,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.EffRR, $r.PF, $r.Trades) -ForegroundColor $c
}

$configs = @(
    [ordered]@{ label="base(no filter)";    slope="false"; spread="false"; min=0 },
    [ordered]@{ label="ADX slope only";      slope="true";  spread="false"; min=0 },
    [ordered]@{ label="DI spread 2.0 only";  slope="false"; spread="true";  min=2.0 },
    [ordered]@{ label="DI spread 3.0 only";  slope="false"; spread="true";  min=3.0 },
    [ordered]@{ label="slope + spread 2.0";  slope="true";  spread="true";  min=2.0 },
    [ordered]@{ label="slope + spread 3.0";  slope="true";  spread="true";  min=3.0 }
)

Write-Host ""
Write-Host "=== DMI_Cross フィルター強度チューニング (USDJPY H4, 過去5年) ===" -ForegroundColor Cyan
Write-Host "  (取引数<20はグレー＝サンプル不足)" -ForegroundColor DarkGray
foreach ($cfg in $configs) {
    $r = Run-DMI $cfg.slope $cfg.spread $cfg.min
    Show $cfg.label $r
}
Write-Host ""
Write-Host "  [基準] 改善前(素クロス): +13,667 / Win 37.9% / PF 1.16 / 132 tr" -ForegroundColor Gray
Write-Host "Done!" -ForegroundColor Green
