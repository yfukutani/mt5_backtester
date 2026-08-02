# test_heartbeat_lib.ps1 -- self-contained tests for heartbeat_lib.ps1 (S-7)
#
# Builds mock launcher_log.txt files and exercises the gap detection and the FX-week
# overlap maths, including a replay of the real 2026-07-31 .. 2026-08-02 outage.
#   powershell -NoProfile -ExecutionPolicy Bypass -File ops\test_heartbeat_lib.ps1
# Exit code 0 = all green, 1 = at least one failure. ASCII only, PowerShell 5.1.

param([string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'heartbeat_lib_test'))

Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'heartbeat_lib.ps1')

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

function New-MockLog {
    # $Times = array of [datetime] at which a watchdog run marker should appear.
    param([string]$Name, [datetime[]]$Times, [string[]]$ExtraLines = @())
    if (-not (Test-Path $WorkDir)) { New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null }
    $path = Join-Path $WorkDir ($Name + '.txt')
    $lines = @()
    foreach ($t in $Times) {
        $stamp = $t.ToString('yyyy-MM-dd HH:mm:ss')
        $lines += ($stamp + ' === watchdog run ===')
        $lines += ($stamp + ' [OANDA_FX] OK - EA loaded (journal evidence) (untouched)')
        $lines += ($stamp + ' === watchdog run: all clear ===')
    }
    $lines += $ExtraLines
    [System.IO.File]::WriteAllText($path, (($lines -join "`r`n") + "`r`n"), [System.Text.Encoding]::UTF8)
    return $path
}

if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null

Write-Output 'ConvertTo-WatchdogRunTimes'
# ---------------------------------------------------------------------------
$base = Get-Date '2026-07-28 00:05:59'   # a Tuesday
$times = @(0..5 | ForEach-Object { $base.AddMinutes(30 * $_) })
$p = New-MockLog -Name 'clean' -Times $times
$rt = ConvertTo-WatchdogRunTimes -LogPath $p
Assert-Equal 6 $rt.Count 'h-1 six run markers parsed'
Assert-Equal $base $rt[0] 'h-2 first marker time correct'

$p = New-MockLog -Name 'noise' -Times @($base) -ExtraLines @(
    '2026-07-28 03:00:00 [XM] PROBLEM DETECTED - terminal process not running. Recovering...',
    'garbage line with no timestamp',
    '2026-07-28 04:00:00 === watchdog run: all clear ===')
$rt = ConvertTo-WatchdogRunTimes -LogPath $p
Assert-Equal 1 $rt.Count 'h-3 only "=== watchdog run ===" counts, not recovery/all-clear lines'

$rt = ConvertTo-WatchdogRunTimes -LogPath (Join-Path $WorkDir 'does_not_exist.txt')
Assert-Equal 0 $rt.Count 'h-4 missing log file -> empty list, no throw'

Write-Output ''
Write-Output 'Get-MarketOverlapMinutes (FX week = Mon 06:00 .. Sat 06:00 JST)'
# ---------------------------------------------------------------------------
$tueAM = Get-Date '2026-07-28 09:00:00'   # Tuesday
Assert-Equal 180 (Get-MarketOverlapMinutes -Start $tueAM -End $tueAM.AddHours(3)) 'm-1 3h on Tuesday = 180 market min'

$sat = Get-Date '2026-08-01 08:00:00'     # Saturday after 06:00 -> closed
Assert-Equal 0 (Get-MarketOverlapMinutes -Start $sat -End $sat.AddHours(10)) 'm-2 Saturday daytime = 0 market min'

$sun = Get-Date '2026-08-02 09:00:00'     # Sunday -> closed
Assert-Equal 0 (Get-MarketOverlapMinutes -Start $sun -End $sun.AddHours(6)) 'm-3 Sunday = 0 market min'

$monEarly = Get-Date '2026-08-03 04:00:00'  # Monday 04:00 -> 08:00, opens at 06:00
Assert-Equal 120 (Get-MarketOverlapMinutes -Start $monEarly -End $monEarly.AddHours(4)) 'm-4 Mon 04-08 = 120 market min'

$satEarly = Get-Date '2026-08-01 04:00:00'  # Saturday 04:00 -> 08:00, closes at 06:00
Assert-Equal 120 (Get-MarketOverlapMinutes -Start $satEarly -End $satEarly.AddHours(4)) 'm-5 Sat 04-08 = 120 market min'

Assert-Equal 0 (Get-MarketOverlapMinutes -Start $tueAM -End $tueAM) 'm-6 zero-length interval = 0'
Assert-Equal 0 (Get-MarketOverlapMinutes -Start $tueAM -End $tueAM.AddHours(-2)) 'm-7 End before Start = 0'

Write-Output ''
Write-Output 'Get-WatchdogGaps'
# ---------------------------------------------------------------------------
$p = New-MockLog -Name 'clean2' -Times $times
$rt = ConvertTo-WatchdogRunTimes -LogPath $p
$g = Get-WatchdogGaps -RunTimes $rt -MaxGapMinutes 90 -Now $rt[$rt.Count-1].AddMinutes(20)
Assert-Equal 0 $g.Count 'g-1 regular 30-min cadence -> no gaps'

$holed = @($base, $base.AddMinutes(30), $base.AddHours(5), $base.AddHours(5.5))
$p = New-MockLog -Name 'holed' -Times $holed
$rt = ConvertTo-WatchdogRunTimes -LogPath $p
$g = Get-WatchdogGaps -RunTimes $rt -MaxGapMinutes 90 -Now $holed[3].AddMinutes(20)
Assert-Equal 1 $g.Count 'g-2 one 4h30m hole detected'
Assert-Equal 270 $g[0].Minutes 'g-3 hole length = 270 min'
Assert-Equal $false $g[0].Ongoing 'g-4 hole is a past gap, not ongoing'

$g = Get-WatchdogGaps -RunTimes $rt -MaxGapMinutes 90 -Now $holed[3].AddHours(6)
Assert-Equal 2 $g.Count 'g-5 trailing silence adds an ongoing gap'
Assert-Equal $true $g[$g.Count-1].Ongoing 'g-6 last gap flagged Ongoing'

$g = Get-WatchdogGaps -RunTimes $rt -MaxGapMinutes 600 -Now $holed[3].AddMinutes(20)
Assert-Equal 0 $g.Count 'g-7 threshold above hole size -> no gaps'

$empty = New-Object System.Collections.Generic.List[datetime]
$g = Get-WatchdogGaps -RunTimes $empty -MaxGapMinutes 90 -Now $base
Assert-Equal 0 $g.Count 'g-8 empty run list -> no gaps, no throw'

Write-Output ''
Write-Output 'Replay of the real 2026-07-31 outage'
# ---------------------------------------------------------------------------
# Watchdog ran every 30 min up to 2026-07-31 11:05:59 (Friday), then nothing until
# 2026-08-02 17:06:01 (Sunday) = 54h00m02s of watchdog silence. (The terminals' own
# downtime was slightly shorter, 53h36m, because they died at 11:30 when the PC
# rebooted - after the watchdog's last successful run.)
$outageTimes = @()
$t = Get-Date '2026-07-31 00:05:59'
while ($t -le (Get-Date '2026-07-31 11:05:59')) { $outageTimes += $t; $t = $t.AddMinutes(30) }
$outageTimes += (Get-Date '2026-08-02 17:06:01')
$p = New-MockLog -Name 'outage' -Times $outageTimes
$rt = ConvertTo-WatchdogRunTimes -LogPath $p
$g = Get-WatchdogGaps -RunTimes $rt -MaxGapMinutes 90 -Now (Get-Date '2026-08-02 17:20:00')
Assert-Equal 1 $g.Count 'r-1 exactly one gap found'
Assert-Equal 3240 $g[0].Minutes 'r-2 gap length = 3240 min (54h00m)'
# Market time lost: Fri 11:05:59 -> Sat 06:00 = 18h54m01s = 1134 min. Sat 06:00 on is closed.
Assert-Equal 1134 $g[0].MarketMinutes 'r-3 1134 market minutes lost (rest of Friday session)'
Assert-Equal $false $g[0].Ongoing 'r-4 gap already closed by the 08-02 run'

$h = Test-WatchdogHeartbeat -LogPath $p -MaxGapMinutes 90 -Now (Get-Date '2026-08-02 17:20:00') -SkipTaskCheck
Assert-Equal 'NOTIFY' $h.Status 'r-5 heartbeat reports NOTIFY for the outage'
Assert-Equal 1 $h.Reasons.Count 'r-6 one reason line'
Assert-Equal $true ($h.Reasons[0] -like '*1134 min inside market hours*') 'r-7 reason names the market-hours cost'

Write-Output ''
Write-Output 'Test-WatchdogHeartbeat happy path'
# ---------------------------------------------------------------------------
$p = New-MockLog -Name 'healthy' -Times $times
$h = Test-WatchdogHeartbeat -LogPath $p -MaxGapMinutes 90 -Now $times[$times.Count-1].AddMinutes(20) -SkipTaskCheck
Assert-Equal 'OK' $h.Status 'p-1 healthy log -> OK'
Assert-Equal 6 $h.RunCount 'p-2 run count reported'
Assert-Equal 0 $h.Reasons.Count 'p-3 no reasons when healthy'

$h = Test-WatchdogHeartbeat -LogPath (Join-Path $WorkDir 'nope.txt') -Now $base -SkipTaskCheck
Assert-Equal 'NOTIFY' $h.Status 'p-4 absent log -> NOTIFY (watchdog never ran)'

Write-Output ''
Write-Output 'Test-WatchdogTaskEnabled (registers a throwaway task, never touches EA-MT5-Watchdog)'
# ---------------------------------------------------------------------------
$probe = 'ZZ-Heartbeat-SelfTest'
$canRegister = $true
try {
    $act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -Command "exit 0"'
    $trg = New-ScheduledTaskTrigger -Daily -At 3am
    Register-ScheduledTask -TaskName $probe -Action $act -Trigger $trg -Force -ErrorAction Stop | Out-Null
} catch { $canRegister = $false }

if (-not $canRegister) {
    Write-Output '  SKIP  cannot register scheduled tasks in this context'
} else {
    # A freshly registered task reports LastTaskResult = 267011 (SCHED_S_TASK_HAS_NOT_RUN).
    # Before the benign-HRESULT fix this scored PROBLEM - the exact false positive seen
    # live on 2026-08-02, where 267009 (SCHED_S_TASK_RUNNING) raised a bogus ALERT.
    $r = Test-WatchdogTaskEnabled -TaskName $probe
    Assert-Equal 'OK' $r.Status 't-1 freshly registered task -> OK (benign SCHED_S_* result)'
    Assert-Equal $true $r.Found 't-2 task reported as found'

    Disable-ScheduledTask -TaskName $probe -ErrorAction SilentlyContinue | Out-Null
    $r = Test-WatchdogTaskEnabled -TaskName $probe
    Assert-Equal 'PROBLEM' $r.Status 't-3 disabled task -> PROBLEM'
    Assert-Equal $true ($r.Reason -like '*DISABLED*') 't-4 reason names DISABLED'

    Unregister-ScheduledTask -TaskName $probe -Confirm:$false -ErrorAction SilentlyContinue
}

$r = Test-WatchdogTaskEnabled -TaskName 'ZZ-Definitely-Not-A-Real-Task'
Assert-Equal 'PROBLEM' $r.Status 't-5 missing task -> PROBLEM'
Assert-Equal $false $r.Found 't-6 missing task reported as not found'

Write-Output ''
Write-Output ('RESULT: pass=' + $script:pass + ' fail=' + $script:fail)
if ($script:fail -gt 0) { exit 1 }
exit 0
