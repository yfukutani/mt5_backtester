# test_watchdog_lib.ps1 -- self-contained tests for watchdog_lib.ps1
#
# Builds mock MT5 terminal data dirs (UTF-16LE journal files in the real tab-separated
# format) and exercises every S-3 / S-4 / A-2 judgement path. Run on any Windows box:
#   powershell -NoProfile -ExecutionPolicy Bypass -File ops\test_watchdog_lib.ps1
# Optional: -WorkDir <dir> to control where mock files are written (default %TEMP%).
# Exit code 0 = all green, 1 = at least one failure. ASCII only, PowerShell 5.1.

param([string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'watchdog_lib_test'))

Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'watchdog_lib.ps1')

$script:pass = 0
$script:fail = 0

function Assert-Equal {
    param($Expected, $Actual, [string]$Label)
    if ("$Expected" -eq "$Actual") {
        $script:pass++
        Write-Output ("  PASS  " + $Label)
    }
    else {
        $script:fail++
        Write-Output ("  FAIL  " + $Label + "  expected=[" + $Expected + "] actual=[" + $Actual + "]")
    }
}

function New-JournalLine {
    param([string]$Time, [string]$Category, [string]$Message)
    return (@('QP', '0', $Time, $Category, $Message) -join "`t")
}

function Write-Journal {
    # Write journal lines as UTF-16LE with BOM (matches real MT5 logs\*.log encoding).
    param([string]$DataDir, [datetime]$Day, [string[]]$Lines)
    $dir = Join-Path $DataDir 'logs'
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $path = Join-Path $dir ($Day.ToString('yyyyMMdd') + '.log')
    [System.IO.File]::WriteAllText($path, (($Lines -join "`r`n") + "`r`n"), [System.Text.Encoding]::Unicode)
}

function New-MockTerminal {
    param([string]$Name)
    $dir = Join-Path $WorkDir $Name
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Path (Join-Path $dir 'logs') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $dir 'MQL5\Files') -Force | Out-Null
    return @{
        Name              = $Name
        DataDir           = $dir
        ProcessPath       = 'C:\mock\terminal64.exe'
        EaPattern         = 'MIX_EA(_OANDA)?'
        ExpectedInstances = 1
    }
}

$startLine = New-JournalLine '13:05:10.100' 'Terminal' 'XMTrading MT5 x64 build 5836 started for Tradexfin Limited'
$iniLine   = New-JournalLine '13:05:09.900' 'Startup'  'successfully initialized from start config "C:\ops\claude_startup_xm_v13.ini"'

Write-Output '=== S-3: date rollover survival ==='

# Case 1: THE bug scenario. Healthy terminal, EA loaded yesterday 13:05, no today log yet.
# Watchdog fires at 00:06. Old logic -> false PROBLEM. New logic must say OK.
$t = New-MockTerminal 'case1'
$yday = (Get-Date).Date.AddDays(-1)
Write-Journal $t.DataDir $yday @(
    $iniLine, $startLine,
    (New-JournalLine '13:05:15.490' 'Experts' 'expert MIX_EA (USDJPY,M15) loaded successfully')
)
$now = (Get-Date).Date.AddMinutes(6)   # today 00:06, today log absent
$r = Test-EaHealth -Terminal $t -Now $now -ProcessRunning $true
Assert-Equal 'OK' $r.Status 'case1 rollover: healthy terminal at 00:06 with no today log -> OK'
Assert-Equal 1 $r.InstanceCount 'case1 rollover: instance count 1'

# Case 2: EA really removed yesterday evening -> PROBLEM (true detection kept).
$t = New-MockTerminal 'case2'
Write-Journal $t.DataDir $yday @(
    $iniLine, $startLine,
    (New-JournalLine '13:05:15.490' 'Experts' 'expert MIX_EA (USDJPY,M15) loaded successfully'),
    (New-JournalLine '22:40:00.000' 'Experts' 'expert MIX_EA (USDJPY,M15) removed')
)
$now = (Get-Date).Date.AddMinutes(30)  # today 00:30, outside rollover window
$r = Test-EaHealth -Terminal $t -Now $now -ProcessRunning $true
Assert-Equal 'PROBLEM' $r.Status 'case2 removal detected across midnight -> PROBLEM'
Assert-Equal 0 $r.InstanceCount 'case2 instance count 0'

# Case 3: removal inside the rollover window is only suppressed, not lost.
$r = Test-EaHealth -Terminal $t -Now ((Get-Date).Date.AddMinutes(6)) -ProcessRunning $true
Assert-Equal 'SKIP' $r.Status 'case3 same removal at 00:06 -> SKIP (suppressed, next run will catch)'

Write-Output '=== S-4: instance count ==='

# Case 4: the actual 07-21 XM pattern -- ini chart AND profile chart both load -> PROBLEM.
$t = New-MockTerminal 'case4'
$today = (Get-Date).Date
Write-Journal $t.DataDir $today @(
    (New-JournalLine '00:06:10.742' 'Startup' 'successfully initialized from start config "C:\ops\claude_startup_xm_v13.ini"'),
    (New-JournalLine '00:06:11.000' 'Terminal' 'XMTrading MT5 x64 build 5836 started for Tradexfin Limited'),
    (New-JournalLine '00:06:15.490' 'Experts' 'expert MIX_EA (EURUSD,H1) loaded successfully'),
    (New-JournalLine '00:06:16.200' 'Experts' 'expert MIX_EA (USDJPY,M15) loaded successfully')
)
$r = Test-EaHealth -Terminal $t -Now ($today.AddMinutes(30)) -ProcessRunning $true
Assert-Equal 'PROBLEM' $r.Status 'case4 duplicate instances -> PROBLEM'
Assert-Equal 2 $r.InstanceCount 'case4 instance count 2'

# Case 5: over-count is positive evidence -> NOT suppressed even inside rollover window.
$r = Test-EaHealth -Terminal $t -Now ($today.AddMinutes(10)) -ProcessRunning $true
Assert-Equal 'PROBLEM' $r.Status 'case5 duplicate instances at 00:10 -> still PROBLEM'

# Case 6: healthy restart pattern (removed then re-loaded once) -> OK, count 1.
$t = New-MockTerminal 'case6'
Write-Journal $t.DataDir $yday @(
    $iniLine, $startLine,
    (New-JournalLine '13:05:15.490' 'Experts' 'expert MIX_EA_OANDA (USDJPY,M15) loaded successfully')
)
Write-Journal $t.DataDir $today @(
    (New-JournalLine '00:05:59.966' 'Experts' 'expert MIX_EA_OANDA (USDJPY,M15) removed'),
    (New-JournalLine '00:06:10.742' 'Startup' 'successfully initialized from start config "C:\ops\claude_startup_oanda.ini"'),
    (New-JournalLine '00:06:11.000' 'Terminal' 'OANDA MetaTrader 5 x64 build 5836 started for OANDA Japan'),
    (New-JournalLine '00:06:15.490' 'Experts' 'expert MIX_EA_OANDA (USDJPY,M15) loaded successfully')
)
$r = Test-EaHealth -Terminal $t -Now ($today.AddMinutes(30)) -ProcessRunning $true
Assert-Equal 'OK' $r.Status 'case6 restart then single reload -> OK'
Assert-Equal 1 $r.InstanceCount 'case6 instance count 1'

Write-Output '=== restart edge cases ==='

# Case 7: terminal just restarted, EA not loaded yet -> GRACE (not PROBLEM).
$t = New-MockTerminal 'case7'
$now = $today.AddHours(12)
Write-Journal $t.DataDir $today @(
    (New-JournalLine '11:55:00.000' 'Startup' 'successfully initialized from start config "C:\ops\x.ini"'),
    (New-JournalLine '11:55:01.000' 'Terminal' 'XMTrading MT5 x64 build 5836 started for Tradexfin Limited')
)
$r = Test-EaHealth -Terminal $t -Now ($today.AddHours(11).AddMinutes(59)) -ProcessRunning $true
Assert-Equal 'GRACE' $r.Status 'case7 restart 4min ago without EA -> GRACE'

# Case 8: same but 30 minutes later -> PROBLEM (EA lost by the restart).
$r = Test-EaHealth -Terminal $t -Now ($today.AddHours(12).AddMinutes(25)) -ProcessRunning $true
Assert-Equal 'PROBLEM' $r.Status 'case8 restart 30min ago without EA -> PROBLEM'

# Case 9: session start wipes older load events (EA was loaded before the restart only).
$t = New-MockTerminal 'case9'
Write-Journal $t.DataDir $today @(
    (New-JournalLine '08:00:00.000' 'Experts' 'expert MIX_EA (USDJPY,M15) loaded successfully'),
    (New-JournalLine '11:55:00.000' 'Terminal' 'XMTrading MT5 x64 build 5836 started for Tradexfin Limited')
)
$r = Test-EaHealth -Terminal $t -Now ($today.AddHours(13)) -ProcessRunning $true
Assert-Equal 'PROBLEM' $r.Status 'case9 pre-restart load does not count for current session -> PROBLEM'

Write-Output '=== process and freshness fallback ==='

# Case 10: process dead -> PROBLEM immediately, even at 00:06.
$t = New-MockTerminal 'case10'
$r = Test-EaHealth -Terminal $t -Now ($today.AddMinutes(6)) -ProcessRunning $false
Assert-Equal 'PROBLEM' $r.Status 'case10 dead process at 00:06 -> PROBLEM (never suppressed)'

# Case 11: very long uptime, journal quiet for 14 days, mixlog fresh -> OK via fallback.
$t = New-MockTerminal 'case11'
$mix = Join-Path $t.DataDir ('MQL5\Files\mixlog_' + (Get-Date).ToString('yyyyMM') + '.csv')
'time,type,magic,symbol,f1,f2,f3,f4,f5,f6,note' | Set-Content -Path $mix -Encoding Ascii
(Get-Item $mix).LastWriteTime = ($today.AddHours(12)).AddHours(-2)
$r = Test-EaHealth -Terminal $t -Now ($today.AddHours(12)) -ProcessRunning $true
Assert-Equal 'OK' $r.Status 'case11 no journal evidence but mixlog 2h fresh -> OK'

# Case 12: same but mixlog 100h stale -> PROBLEM (outside rollover window).
(Get-Item $mix).LastWriteTime = ($today.AddHours(12)).AddHours(-100)
$r = Test-EaHealth -Terminal $t -Now ($today.AddHours(12)) -ProcessRunning $true
Assert-Equal 'PROBLEM' $r.Status 'case12 no evidence and mixlog 100h stale -> PROBLEM'

# Case 13: per-terminal MixlogPrefix override (OANDA terminals write mixlog_oa_*.csv).
$t = New-MockTerminal 'case13'
$t.MixlogPrefix = 'mixlog_oa'
$mix = Join-Path $t.DataDir ('MQL5\Files\mixlog_oa_' + (Get-Date).ToString('yyyyMM') + '.csv')
'time,type,magic,symbol,f1,f2,f3,f4,f5,f6,note' | Set-Content -Path $mix -Encoding Ascii
(Get-Item $mix).LastWriteTime = ($today.AddHours(12)).AddHours(-2)
$r = Test-EaHealth -Terminal $t -Now ($today.AddHours(12)) -ProcessRunning $true
Assert-Equal 'OK' $r.Status 'case13 mixlog_oa prefix honored for freshness fallback -> OK'

Write-Output '=== A-2: daily health log ==='

$hl = Join-Path $WorkDir 'health_log.md'
$mon = (Get-Date).Date
while ($mon.DayOfWeek -ne 'Monday') { $mon = $mon.AddDays(-1) }   # a known weekday

('# health log', ('- ' + $mon.ToString('yyyy-MM-dd') + ' all clear')) | Set-Content -Path $hl -Encoding Ascii
$r = Test-HealthLogToday -HealthLogPath $hl -Now ($mon.AddHours(20).AddMinutes(30))
Assert-Equal 'OK' $r.Status 'a2-1 entry present at 20:30 weekday -> OK'

('# health log', '- 2001-01-01 old entry') | Set-Content -Path $hl -Encoding Ascii
$r = Test-HealthLogToday -HealthLogPath $hl -Now ($mon.AddHours(20).AddMinutes(30))
Assert-Equal 'NOTIFY' $r.Status 'a2-2 entry missing at 20:30 weekday -> NOTIFY'

$r = Test-HealthLogToday -HealthLogPath $hl -Now ($mon.AddHours(19))
Assert-Equal 'OK' $r.Status 'a2-3 entry missing but before 20:00 -> OK (not yet due)'

$sun = $mon.AddDays(-1)
$r = Test-HealthLogToday -HealthLogPath $hl -Now ($sun.AddHours(21))
Assert-Equal 'OK' $r.Status 'a2-4 weekend -> OK (not checked)'

Write-Output '=== A-2: weekly artifacts ==='

$rep = Join-Path $WorkDir 'reports'
if (-not (Test-Path $rep)) { New-Item -ItemType Directory -Path $rep -Force | Out-Null }
$sat = (Get-Date).Date
while ($sat.DayOfWeek -ne 'Saturday') { $sat = $sat.AddDays(-1) }
$stamp = $sat.ToString('yyyy-MM-dd')

New-Item -ItemType File -Path (Join-Path $rep ($stamp + '_weekly.md')) -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $rep ($stamp + '_improvements.md')) -Force | Out-Null
$r = Test-WeeklyArtifacts -ReportsDir $rep -Now ($sat.AddHours(14).AddMinutes(30))
Assert-Equal 'OK' $r.Status 'a2-5 both reports present Sat 14:30 -> OK'

Remove-Item (Join-Path $rep ($stamp + '_improvements.md')) -Force
$r = Test-WeeklyArtifacts -ReportsDir $rep -Now ($sat.AddHours(14).AddMinutes(30))
Assert-Equal 'NOTIFY' $r.Status 'a2-6 improvements report missing Sat 14:30 -> NOTIFY'

$r = Test-WeeklyArtifacts -ReportsDir $rep -Now ($sat.AddHours(13))
Assert-Equal 'OK' $r.Status 'a2-7 before 14:00 -> OK (not yet due)'

$fri = $sat.AddDays(-1)
$r = Test-WeeklyArtifacts -ReportsDir $rep -Now ($fri.AddHours(15))
Assert-Equal 'OK' $r.Status 'a2-8 not Saturday -> OK (not checked)'

Write-Output ''
Write-Output ('RESULT: pass=' + $script:pass + ' fail=' + $script:fail)
if ($script:fail -gt 0) { exit 1 }
exit 0
