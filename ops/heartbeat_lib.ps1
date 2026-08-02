# heartbeat_lib.ps1 - S-7: detect that the EA watchdog itself stopped running.
#
# Why this exists (incident 2026-07-31 .. 2026-08-02, see
# docs/forward_reports/2026-08-02_improvements.md F-1 / F-2):
#   A Windows Update reboot killed all three MT5 terminals at 2026-07-31 11:30 JST.
#   The PC came back up and stayed up, but the EA-MT5-Watchdog task never ran again
#   for 53h36m because it is registered with LogonType=InteractiveToken and nobody
#   logged on. All three terminals stayed dead through the whole Friday session.
#
#   The A-2 freshness checks that should have caught this live INSIDE
#   check_and_recover.ps1 - the very process that was dead. A monitor co-hosted with
#   the thing it monitors cannot report that thing's death. This library is the
#   separated check: it looks at launcher_log.txt from the OUTSIDE and reports gaps.
#
# Scope note: without administrator rights the runner can only be registered as an
# ordinary interactive-token task, so it too is asleep while nobody is logged on.
# That is accepted and by design here: the value is RETROSPECTIVE detection. The
# moment a session exists again, the gap is found, written to a durable log and
# surfaced - instead of being silently buried as it was for 54 hours.
#
# ASCII-only, like check_and_recover.ps1: Windows PowerShell 5.1 on this PC
# misparses Japanese string literals in a BOM-less UTF-8 .ps1.

Set-StrictMode -Version 2.0

function ConvertTo-WatchdogRunTimes {
    # Parse launcher_log.txt and return the sorted [datetime] of each "=== watchdog run ==="
    # marker. Any other line is ignored, so recovery/notice lines cannot inflate the count.
    param(
        [Parameter(Mandatory=$true)][string] $LogPath,
        [int] $TailLines = 20000
    )
    $times = New-Object System.Collections.Generic.List[datetime]
    if (-not (Test-Path -LiteralPath $LogPath)) { return ,$times }

    $lines = Get-Content -LiteralPath $LogPath -Tail $TailLines -ErrorAction SilentlyContinue
    if ($null -eq $lines) { return ,$times }

    foreach ($line in $lines) {
        if ($line -match '^(?<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+===\s+watchdog run\s+===') {
            $parsed = [datetime]::MinValue
            $ok = [datetime]::TryParseExact(
                $Matches['ts'], 'yyyy-MM-dd HH:mm:ss',
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::None, [ref]$parsed)
            if ($ok) { $times.Add($parsed) | Out-Null }
        }
    }
    $sorted = New-Object System.Collections.Generic.List[datetime]
    foreach ($t in ($times | Sort-Object)) { $sorted.Add($t) | Out-Null }
    # Comma wrap: PowerShell unrolls a single-element collection on return, which would
    # hand the caller a bare [datetime] with no .Count and break every caller downstream.
    return ,$sorted
}

function Get-MarketOverlapMinutes {
    # Minutes of [Start,End) that fall inside the FX week, expressed in JST wall clock:
    # open Monday 06:00 JST, close Saturday 06:00 JST. Used to rank a gap's severity -
    # a 50-hour weekend gap costs nothing, a 3-hour Tuesday gap costs real signals.
    param(
        [Parameter(Mandatory=$true)][datetime] $Start,
        [Parameter(Mandatory=$true)][datetime] $End
    )
    if ($End -le $Start) { return 0 }

    # Walk calendar days and intersect exactly with that day's open window. An earlier
    # version sampled the midpoint of 1-hour steps, which silently rounded any gap that
    # started or ended mid-hour (it scored the real outage 1140 min instead of 1134).
    $total = 0.0
    $day = $Start.Date
    while ($day -lt $End) {
        $dow = [int]$day.DayOfWeek          # Sunday=0 .. Saturday=6
        $openFrom = $day
        $openTo   = $day.AddDays(1)
        switch ($dow) {
            0 { $openTo   = $day }                   # Sunday: closed all day
            1 { $openFrom = $day.AddHours(6) }       # Monday: opens 06:00
            6 { $openTo   = $day.AddHours(6) }       # Saturday: closes 06:00
        }
        if ($openTo -gt $openFrom) {
            $lo = $(if ($Start -gt $openFrom) { $Start } else { $openFrom })
            $hi = $(if ($End   -lt $openTo)   { $End }   else { $openTo })
            if ($hi -gt $lo) { $total += ($hi - $lo).TotalMinutes }
        }
        $day = $day.AddDays(1)
    }
    return [int][math]::Round($total)
}

function Get-WatchdogGaps {
    # Return every interval between consecutive watchdog runs that exceeds
    # -MaxGapMinutes, plus the trailing "still silent right now" interval.
    param(
        # AllowEmptyCollection: a mandatory collection parameter otherwise rejects an
        # empty list, which is exactly the "watchdog has never run" case we must handle.
        [Parameter(Mandatory=$true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[datetime]] $RunTimes,
        [int] $MaxGapMinutes = 90,
        [datetime] $Now = (Get-Date)
    )
    $gaps = @()
    if ($RunTimes.Count -eq 0) { return ,$gaps }

    for ($i = 1; $i -lt $RunTimes.Count; $i++) {
        $from = $RunTimes[$i-1]
        $to   = $RunTimes[$i]
        $mins = [int][math]::Round(($to - $from).TotalMinutes)
        if ($mins -gt $MaxGapMinutes) {
            $gaps += [pscustomobject]@{
                From           = $from
                To             = $to
                Minutes        = $mins
                MarketMinutes  = (Get-MarketOverlapMinutes -Start $from -End $to)
                Ongoing        = $false
            }
        }
    }

    $last = $RunTimes[$RunTimes.Count - 1]
    $trailing = [int][math]::Round(($Now - $last).TotalMinutes)
    if ($trailing -gt $MaxGapMinutes) {
        $gaps += [pscustomobject]@{
            From           = $last
            To             = $Now
            Minutes        = $trailing
            MarketMinutes  = (Get-MarketOverlapMinutes -Start $last -End $Now)
            Ongoing        = $true
        }
    }
    # Comma wrap for the same single-element unrolling reason as ConvertTo-WatchdogRunTimes.
    return ,$gaps
}

function Test-WatchdogTaskEnabled {
    # The other way the safety net can die: the task still exists but is Disabled,
    # or its last run failed. check_and_recover.ps1 cannot report either condition.
    param([string] $TaskName = 'EA-MT5-Watchdog')

    $result = [pscustomobject]@{
        Found          = $false
        State          = 'Unknown'
        LastRunTime    = $null
        LastTaskResult = $null
        Status         = 'PROBLEM'
        Reason         = ''
    }
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    } catch {
        $result.Reason = ("scheduled task '{0}' not found - the watchdog is not registered at all" -f $TaskName)
        return $result
    }

    $result.Found = $true
    $result.State = [string]$task.State
    try {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
        $result.LastRunTime    = $info.LastRunTime
        $result.LastTaskResult = $info.LastTaskResult
    } catch {}

    if ($result.State -eq 'Disabled') {
        $result.Reason = ("scheduled task '{0}' is DISABLED" -f $TaskName)
        return $result
    }
    # LastTaskResult is not just a process exit code - the scheduler also stores
    # informational SCHED_S_* HRESULTs there. Treating "non-zero = broken" fires a false
    # alarm every single time the check happens to run while the watchdog is mid-run
    # (seen live on 2026-08-02: 267009). Only genuinely bad values escalate.
    #   0      = success
    #   267009 = 0x00041301 SCHED_S_TASK_RUNNING       (running right now)
    #   267011 = 0x00041303 SCHED_S_TASK_HAS_NOT_RUN   (registered, first run pending)
    #   267012 = 0x00041304 SCHED_S_TASK_NO_MORE_RUNS  (trigger exhausted)
    $benignResults = @(0, 267009, 267011, 267012)
    if ($null -ne $result.LastTaskResult -and $benignResults -notcontains $result.LastTaskResult) {
        $result.Reason = ("scheduled task '{0}' last exit code = {1}" -f $TaskName, $result.LastTaskResult)
        return $result
    }

    $result.Status = 'OK'
    $result.Reason = ("scheduled task '{0}' state={1}" -f $TaskName, $result.State)
    return $result
}

function Test-WatchdogHeartbeat {
    # Top-level judgement. Returns Status OK / NOTIFY plus the gap list, so the
    # runner decides what to log and what to escalate.
    param(
        [Parameter(Mandatory=$true)][string] $LogPath,
        [int] $MaxGapMinutes = 90,
        [datetime] $Now = (Get-Date),
        [string] $TaskName = 'EA-MT5-Watchdog',
        [switch] $SkipTaskCheck
    )
    $runTimes = ConvertTo-WatchdogRunTimes -LogPath $LogPath
    $gaps = Get-WatchdogGaps -RunTimes $runTimes -MaxGapMinutes $MaxGapMinutes -Now $Now

    $taskState = $null
    if (-not $SkipTaskCheck) { $taskState = Test-WatchdogTaskEnabled -TaskName $TaskName }

    $reasons = @()
    foreach ($g in $gaps) {
        $tag = if ($g.Ongoing) { 'ONGOING' } else { 'past' }
        $reasons += ("{0} gap {1} min ({2} min inside market hours) from {3} to {4}" -f `
            $tag, $g.Minutes, $g.MarketMinutes,
            $g.From.ToString('yyyy-MM-dd HH:mm'), $g.To.ToString('yyyy-MM-dd HH:mm'))
    }
    if ($null -ne $taskState -and $taskState.Status -ne 'OK') { $reasons += $taskState.Reason }
    if ($runTimes.Count -eq 0) { $reasons += ("no watchdog run markers found in {0}" -f $LogPath) }

    $status = 'OK'
    if ($reasons.Count -gt 0) { $status = 'NOTIFY' }

    return [pscustomobject]@{
        Status    = $status
        Gaps      = $gaps
        TaskState = $taskState
        RunCount  = $runTimes.Count
        LastRun   = $(if ($runTimes.Count -gt 0) { $runTimes[$runTimes.Count-1] } else { $null })
        Reasons   = $reasons
    }
}
