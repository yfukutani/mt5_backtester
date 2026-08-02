# watchdog_lib.ps1 -- helper library for check_and_recover.ps1
#
# Implements the 2026-07-25 improvement items (docs/forward_reports/2026-07-25_improvements.md):
#   S-3 : EA-loaded judgement that survives the date rollover (no more 00:06 false restarts)
#   S-4 : "one terminal = one EA instance" check (over-count detection)
#   A-2 : daily health-log freshness check + weekly report artifact existence check
#
# Windows PowerShell 5.1 compatible. ASCII only (Japanese in .ps1 breaks 5.1 parsing).
# Integration: dot-source this file from check_and_recover.ps1 and call Test-EaHealth
# instead of the old Test-EaLoaded. See docs/ops_fix_20260725.md for the exact steps.
#
# Terminal descriptor (hashtable or PSCustomObject) used by Test-EaHealth:
#   Name              display name, e.g. 'XM'
#   DataDir           MT5 data dir containing 'logs\' and 'MQL5\Files\'
#   ProcessPath       full path of this terminal's terminal64.exe (process identity)
#   EaPattern         regex fragment matching the EA name, e.g. 'MIX_EA' or 'MIX_EA_OANDA'
#   ExpectedInstances expected number of attached EA charts (1 for all three terminals)
#
# Status values returned:
#   OK      healthy, do nothing
#   GRACE   terminal started moments ago, EA init still pending -> do nothing, recheck later
#   SKIP    judgement suppressed inside the 00:00-00:15 rollover window -> do nothing
#   PROBLEM genuine anomaly -> hand over to the existing recovery / notification path
#
# Design notes:
# - The old Test-EaLoaded read only today's logs\<yyyyMMdd>.log. Right after midnight that
#   file does not exist yet (or has no 'loaded successfully' line), so every healthy
#   terminal was judged dead once per day at 00:05:59 (15/15 false positives in week 3).
# - This library instead scans up to -DaysBack days of journal files, finds the last
#   terminal session start marker and the last per-chart EA load/remove events, and only
#   then decides. A missing today-file is no longer an error condition.
# - The instance count is derived from the same event scan: charts whose LAST event is
#   'loaded successfully' within the current session. Count > expected => PROBLEM (S-4).
# - Process-dead is always PROBLEM (that check does not depend on log files).
#   Log-dependent PROBLEMs are downgraded to SKIP inside 00:00-00:15 as a belt-and-braces
#   guard (S-3 fix candidate (c)); over-count is kept as PROBLEM because it is positive
#   evidence, not an absence-of-evidence judgement.

Set-StrictMode -Version 2

function ConvertTo-JournalRecords {
    # Parse terminal journal files (logs\<yyyyMMdd>.log, UTF-16LE, tab separated) into
    # objects: Stamp (datetime, local PC time), Category, Message. Oldest first.
    param(
        [Parameter(Mandatory = $true)][string]$LogDir,
        [Parameter(Mandatory = $true)][datetime]$Now,
        [int]$DaysBack = 14
    )
    $records = New-Object System.Collections.Generic.List[object]
    for ($i = $DaysBack - 1; $i -ge 0; $i--) {
        $day = $Now.Date.AddDays(-$i)
        $path = Join-Path $LogDir ($day.ToString('yyyyMMdd') + '.log')
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $lines = $null
        try { $lines = Get-Content -LiteralPath $path -ErrorAction Stop } catch { continue }
        foreach ($ln in @($lines)) {
            if ($null -eq $ln -or $ln.Length -eq 0) { continue }
            $parts = $ln -split "`t"
            if ($parts.Count -lt 5) { continue }
            $t = [datetime]::MinValue
            $ok = [datetime]::TryParseExact($parts[2], 'HH:mm:ss.fff',
                [System.Globalization.CultureInfo]::InvariantCulture,
                [System.Globalization.DateTimeStyles]::None, [ref]$t)
            if (-not $ok) { continue }
            $records.Add([pscustomobject]@{
                Stamp    = $day.Add($t.TimeOfDay)
                Category = $parts[3]
                Message  = (($parts[4..($parts.Count - 1)]) -join "`t")
            })
        }
    }
    return , $records
}

function Get-LastSessionStart {
    # Datetime of the most recent terminal start marker, or $null if none in the window.
    # Markers (both appear at startup, either is sufficient):
    #   Terminal  '... x64 build NNNN started for <Broker>'
    #   Startup   'successfully initialized from start config "<ini>"'
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()]$Records)
    $last = $null
    foreach ($r in $Records) {
        if (($r.Category -eq 'Terminal' -and $r.Message -match 'started for') -or
            ($r.Category -eq 'Startup' -and $r.Message -match 'initialized from start config')) {
            $last = $r.Stamp
        }
    }
    return $last
}

function Get-EaChartMap {
    # Last EA event per chart. Key: '<EaName>|<Symbol>|<TF>', value: 'loaded' or 'removed'.
    # Matches journal lines:  expert MIX_EA (EURUSD,H1) loaded successfully
    #                         expert MIX_EA_OANDA (USDJPY,M15) removed
    # If -Since is given, events before it (previous sessions) are ignored.
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()]$Records,
        [Parameter(Mandatory = $true)][string]$EaPattern,
        [datetime]$Since
    )
    $map = @{}
    # Named groups: $EaPattern itself may contain groups (e.g. 'MIX_EA(_OANDA)?'), which
    # would shift positional capture indexes. Do not add groups named name/sym/tf/action
    # inside EaPattern.
    $rx = '^expert\s+(?<name>' + $EaPattern + ')\s+\((?<sym>[^,\)]+),(?<tf>[^\)]+)\)\s+(?<action>loaded successfully|removed)'
    foreach ($r in $Records) {
        if ($PSBoundParameters.ContainsKey('Since') -and $r.Stamp -lt $Since) { continue }
        if ($r.Message -match $rx) {
            $key = $Matches['name'] + '|' + $Matches['sym'] + '|' + $Matches['tf']
            if ($Matches['action'] -eq 'loaded successfully') { $map[$key] = 'loaded' }
            else { $map[$key] = 'removed' }
        }
    }
    return $map
}

function Get-MixlogLastWrite {
    # Newest LastWriteTime among current-month and previous-month mixlog files
    # (<prefix>_yyyyMM.csv) in the terminal's MQL5\Files. $null if none exist.
    param(
        [Parameter(Mandatory = $true)][string]$FilesDir,
        [string]$Prefix = 'mixlog',
        [Parameter(Mandatory = $true)][datetime]$Now
    )
    $best = $null
    foreach ($m in 0..1) {
        $d = $Now.AddMonths(-$m)
        $p = Join-Path $FilesDir ($Prefix + '_' + $d.ToString('yyyyMM') + '.csv')
        if (Test-Path -LiteralPath $p) {
            $w = (Get-Item -LiteralPath $p).LastWriteTime
            if ($null -eq $best -or $w -gt $best) { $best = $w }
        }
    }
    return $best
}

function Test-InRolloverWindow {
    param([Parameter(Mandatory = $true)][datetime]$Now, [int]$WindowMinutes = 15)
    $t = $Now.TimeOfDay
    return ($t -ge [timespan]::Zero -and $t -lt [timespan]::FromMinutes($WindowMinutes))
}

function Get-LastLiveUpdate {
    # S-8: timestamp of the most recent MT5 LiveUpdate restart marker, or $null.
    # Journal shape (real incident, 2026-08-02):
    #   17:07:04  LiveUpdate  new version build 6090 ... is available
    #   17:07:10  LiveUpdate  downloaded successfully
    #   17:08:10  LiveUpdate  start "...\liveupdate\terminal64.exe" /update /path:... /config:...
    # Only the 'start ... /update' line marks the actual restart; the two lines before it
    # are just the update check and do not by themselves imply the terminal restarted.
    # LiveUpdate restarts the terminal WITHOUT re-attaching the EA even when /config: is
    # passed, so this event belongs to the OLD session -- do not filter by -Since.
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()]$Records)
    $last = $null
    foreach ($r in $Records) {
        if ($r.Category -eq 'LiveUpdate' -and $r.Message -match '/update') {
            $last = $r.Stamp
        }
    }
    return $last
}

function Test-EaHealth {
    # Main S-3 / S-4 judgement for one terminal. See header for the returned Status values.
    # -ProcessRunning: test override; when $null the real process list is queried and the
    #   terminal is identified by executable path (three terminal64.exe may run at once).
    param(
        [Parameter(Mandatory = $true)]$Terminal,
        [datetime]$Now = (Get-Date),
        $ProcessRunning = $null,
        [int]$GraceMinutes = 10,
        [int]$DaysBack = 14,
        [int]$FreshLimitHours = 78,
        [string]$MixlogPrefix = 'mixlog',
        [int]$LiveUpdateWindowMin = 40
    )
    $result = [pscustomobject]@{
        Name           = $Terminal.Name
        Status         = 'OK'
        Reason         = 'EA loaded (journal evidence)'
        InstanceCount  = $null
        SessionStart   = $null
        RolloverWindow = (Test-InRolloverWindow -Now $Now)
    }

    # 1) process existence -- independent of any log file, never suppressed
    $procOk = $ProcessRunning
    if ($null -eq $procOk) {
        $procOk = $false
        $procs = @(Get-Process -Name 'terminal64' -ErrorAction SilentlyContinue)
        foreach ($p in $procs) {
            try { if ($p.Path -eq $Terminal.ProcessPath) { $procOk = $true } } catch { }
        }
    }
    if (-not $procOk) {
        $result.Status = 'PROBLEM'
        $result.Reason = 'terminal process not running'
        return $result
    }

    # 2) journal evidence (today AND previous days -- this is the S-3 fix)
    $records = ConvertTo-JournalRecords -LogDir (Join-Path $Terminal.DataDir 'logs') -Now $Now -DaysBack $DaysBack
    $sessionStart = Get-LastSessionStart -Records $records
    if ($null -ne $sessionStart) {
        $result.SessionStart = $sessionStart
        $map = Get-EaChartMap -Records $records -EaPattern $Terminal.EaPattern -Since $sessionStart
    }
    else {
        $map = Get-EaChartMap -Records $records -EaPattern $Terminal.EaPattern
    }
    $loaded = 0
    foreach ($v in $map.Values) { if ($v -eq 'loaded') { $loaded++ } }

    $expected = 1
    if ($null -ne $Terminal.ExpectedInstances) { $expected = [int]$Terminal.ExpectedInstances }

    $hasEvidence = ($map.Count -gt 0 -or $null -ne $sessionStart)
    if ($hasEvidence) {
        $result.InstanceCount = $loaded
        if ($loaded -eq $expected) { return $result }
        if ($loaded -gt $expected) {
            # S-4: positive evidence of a broken configuration -> never suppressed
            $result.Status = 'PROBLEM'
            $result.Reason = ('EA instance count ' + $loaded + ' exceeds expected ' + $expected + ' (duplicate charts)')
            return $result
        }
        # loaded < expected
        # S-8: a recent MT5 LiveUpdate restart is positive evidence the EA will NOT come
        # back on its own (unlike a normal restart, where grace-period waiting helps while
        # the EA finishes initializing). Never suppressed by GRACE or the rollover SKIP --
        # both exist to avoid false alarms on an otherwise-healthy startup, and this is not
        # that case. See docs/ops_fix_20260802.md S-8 for the 2026-08-02 27-40 minute gap
        # this closes (previously bound to the watchdog's own 30-min cycle).
        $lastLiveUpdate = Get-LastLiveUpdate -Records $records
        if ($null -ne $lastLiveUpdate -and ($Now - $lastLiveUpdate).TotalMinutes -ge 0 -and
            ($Now - $lastLiveUpdate).TotalMinutes -le $LiveUpdateWindowMin) {
            $result.Status = 'PROBLEM'
            $result.Reason = ('MT5 LiveUpdate restart at ' + $lastLiveUpdate.ToString('HH:mm:ss') +
                ' did not re-attach the EA (' + $loaded + '/' + $expected + ' loaded)')
            return $result
        }
        if ($null -ne $sessionStart -and ($Now - $sessionStart).TotalMinutes -lt $GraceMinutes) {
            $result.Status = 'GRACE'
            $result.Reason = 'terminal started recently, EA init pending'
            return $result
        }
        if ($result.RolloverWindow) {
            $result.Status = 'SKIP'
            $result.Reason = 'rollover window (00:00-00:15), log-based judgement suppressed'
            return $result
        }
        $result.Status = 'PROBLEM'
        $result.Reason = ('EA instance count ' + $loaded + ' below expected ' + $expected)
        return $result
    }

    # 3) no journal evidence in the whole window (very long uptime, quiet journal)
    #    -> fall back to mixlog freshness before declaring a problem
    #    Per-terminal prefix override (OANDA terminals use OpsLogPrefix 'mixlog_oa').
    $prefix = $MixlogPrefix
    if ($Terminal -is [hashtable]) {
        if ($Terminal.ContainsKey('MixlogPrefix') -and $Terminal['MixlogPrefix']) { $prefix = $Terminal['MixlogPrefix'] }
    }
    else {
        try { if ($Terminal.MixlogPrefix) { $prefix = $Terminal.MixlogPrefix } } catch { }
    }
    $lw = Get-MixlogLastWrite -FilesDir (Join-Path $Terminal.DataDir 'MQL5\Files') -Prefix $prefix -Now $Now
    if ($null -ne $lw -and ($Now - $lw).TotalHours -le $FreshLimitHours) {
        $result.Reason = ('no journal evidence; mixlog fresh (' + $lw.ToString('yyyy-MM-dd HH:mm') + ')')
        return $result
    }
    if ($result.RolloverWindow) {
        $result.Status = 'SKIP'
        $result.Reason = 'rollover window (00:00-00:15), no evidence available'
        return $result
    }
    $result.Status = 'PROBLEM'
    $result.Reason = 'no EA evidence in journal window and mixlog stale or absent'
    return $result
}

function Test-HealthLogToday {
    # A-2 (1): on weekdays after -DueHour (JST, local clock), health_log.md must already
    # contain an entry for today. Returns Status OK / NOTIFY.
    param(
        [Parameter(Mandatory = $true)][string]$HealthLogPath,
        [datetime]$Now = (Get-Date),
        [int]$DueHour = 20,
        [string[]]$DateFormats = @('yyyy-MM-dd', 'yyyy/MM/dd')
    )
    $r = [pscustomobject]@{ Check = 'health_log daily'; Status = 'OK'; Reason = '' }
    if ($Now.DayOfWeek -eq 'Saturday' -or $Now.DayOfWeek -eq 'Sunday') {
        $r.Reason = 'weekend, not checked'
        return $r
    }
    if ($Now.Hour -lt $DueHour) {
        $r.Reason = ('before due hour ' + $DueHour + ':00')
        return $r
    }
    if (-not (Test-Path -LiteralPath $HealthLogPath)) {
        $r.Status = 'NOTIFY'
        $r.Reason = 'health log file missing'
        return $r
    }
    foreach ($fmt in $DateFormats) {
        $needle = $Now.ToString($fmt)
        if (Select-String -LiteralPath $HealthLogPath -Pattern $needle -SimpleMatch -Quiet) {
            $r.Reason = ('entry found for ' + $needle)
            return $r
        }
    }
    $r.Status = 'NOTIFY'
    $r.Reason = ('no entry for today (' + $Now.ToString($DateFormats[0]) + ') by ' + $DueHour + ':00')
    return $r
}

function Test-WeeklyArtifacts {
    # A-2 (2): on Saturday after -DueHour, this week's weekly + improvements reports must
    # exist as <ReportsDir>\<yyyy-MM-dd>_weekly.md and <yyyy-MM-dd>_improvements.md
    # (dated with Saturday's date). Returns Status OK / NOTIFY.
    param(
        [Parameter(Mandatory = $true)][string]$ReportsDir,
        [datetime]$Now = (Get-Date),
        [int]$DueHour = 14
    )
    $r = [pscustomobject]@{ Check = 'weekly artifacts'; Status = 'OK'; Reason = '' }
    if ($Now.DayOfWeek -ne 'Saturday') {
        $r.Reason = 'not Saturday, not checked'
        return $r
    }
    if ($Now.Hour -lt $DueHour) {
        $r.Reason = ('before due hour ' + $DueHour + ':00')
        return $r
    }
    $stamp = $Now.ToString('yyyy-MM-dd')
    $missing = @()
    foreach ($suffix in @('_weekly.md', '_improvements.md')) {
        $p = Join-Path $ReportsDir ($stamp + $suffix)
        if (-not (Test-Path -LiteralPath $p)) { $missing += ($stamp + $suffix) }
    }
    if ($missing.Count -gt 0) {
        $r.Status = 'NOTIFY'
        $r.Reason = ('missing: ' + ($missing -join ', '))
        return $r
    }
    $r.Reason = ('both reports present for ' + $stamp)
    return $r
}
