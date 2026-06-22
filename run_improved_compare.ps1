# Keltner/DMI 改善前後 + 3つ巴 再比較 — USDJPY H4（過去5年）
# Keltner: リテストON/OFF / DMI: 品質フィルターON/OFF

Set-Location "C:\Users\f\source\repos\mt5_backtester"

$mt5bt      = "C:\Users\f\AppData\Local\Python\pythoncore-3.14-64\Scripts\mt5bt.exe"
$testerRoot = "C:\Users\f\AppData\Roaming\MetaQuotes\Tester\BAC624F09E3C5D5AFDD21CE91C0B879D"

$fromDate = "2021.06.21"
$toDate   = "2026.06.20"

function Parse-Csv($csvName) {
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

function Run-Keltner($retest, $csvName) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""KeltnerBreakout""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  EMA_Period:              20`r`n  ATR_Period:              14`r`n  ChannelMult:             1.5`r`n  UseRetest:               $retest`r`n  Retest_Timeout_Bars:     10`r`n  TrendMA_Period:          200`r`n  UseADXFilter:            true`r`n  ADX_Period:              14`r`n  ADX_Threshold:           22.5`r`n  UseATRStops:             true`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           40`r`n  TakeProfit_Pips:         80`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260625`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""Kelt_imp""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\imp_kelt_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\imp_kelt_tmp.yaml --no-charts 2>&1 | Out-Null
    return Parse-Csv $csvName
}

function Run-DMI($slope, $spread, $csvName) {
    $yaml = "mt5_path: ""C:\\Users\\f\\AppData\\Roaming\\XMTrading MT5\\terminal64.exe""`r`nexpert:    ""DMI_Cross""`r`nsymbol:    ""USDJPY""`r`nperiod:    ""H4""`r`nfrom_date: ""$fromDate""`r`nto_date:   ""$toDate""`r`ndeposit:  100000`r`ncurrency: ""JPY""`r`nleverage: 25`r`nmodel: ""open_prices""`r`nparameters:`r`n  ADX_Period:              14`r`n  ADX_Threshold:           25.0`r`n  UseADXSlope:             $slope`r`n  UseDISpread:             $spread`r`n  DI_Min_Spread:           5.0`r`n  TrendMA_Period:          200`r`n  UseMAFilter:             true`r`n  UseATRStops:             true`r`n  ATR_Period:              14`r`n  ATR_SL_Mult:             2.0`r`n  RR_Ratio:                2.0`r`n  StopLoss_Pips:           40`r`n  TakeProfit_Pips:         80`r`n  LotSize:                 0.01`r`n  MagicNumber:             20260626`r`n  ResultFileName:          ""$csvName""`r`nreport_dir:  ""results""`r`nreport_name: ""DMI_imp""`r`n"
    [System.IO.File]::WriteAllText("C:\Users\f\source\repos\mt5_backtester\configs\imp_dmi_tmp.yaml", $yaml, [System.Text.Encoding]::UTF8)
    & $mt5bt run configs\imp_dmi_tmp.yaml --no-charts 2>&1 | Out-Null
    return Parse-Csv $csvName
}

function Format-Profit($v) { $s = if ($v -ge 0) { "+" } else { "" }; return ("{0}{1:N0}" -f $s, $v) }
function Show($label, $r) {
    if ($null -eq $r) { Write-Host ("  {0,-26} CSV not found" -f $label) -ForegroundColor Yellow; return }
    $c = if ($r.Net -ge 0) { "Green" } else { "Red" }
    Write-Host ("  {0,-26} Net {1,9} | Win {2,5}% | EffRR {3,5} | PF {4,6} | {5,4} tr" -f $label, (Format-Profit $r.Net), $r.WinRate, $r.EffRR, $r.PF, $r.Trades) -ForegroundColor $c
}

Write-Host ""
Write-Host "=== KeltnerBreakout: 改善前(即ブレイク) vs 改善後(リテスト) ===" -ForegroundColor Cyan
$kBase = Run-Keltner "false" "imp_kelt_base.csv"
$kImp  = Run-Keltner "true"  "imp_kelt_retest.csv"
Show "改善前(即ブレイク)" $kBase
Show "改善後(リテスト)"   $kImp

Write-Host ""
Write-Host "=== DMI_Cross: 改善前(素クロス) vs 改善後(品質F) ===" -ForegroundColor Cyan
$dBase = Run-DMI "false" "false" "imp_dmi_base.csv"
$dImp  = Run-DMI "true"  "true"  "imp_dmi_filt.csv"
Show "改善前(素クロス)"   $dBase
Show "改善後(傾き+乖離)"  $dImp

Write-Host ""
Write-Host "===== 改善後 3つ巴 (USDJPY H4, 過去5年) =====" -ForegroundColor Yellow
Write-Host "  PullbackTrend(参考): +43,341 / Win 44.2% / EffRR 1.81 / PF 1.44 (主軸)" -ForegroundColor Gray
Show "KeltnerBreakout v1.1" $kImp
Show "DMI_Cross v1.1"       $dImp
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
