# fix_watchdog_admin.ps1 - S-5 / S-6. MUST be run from an ELEVATED PowerShell.
#
# Both fixes below need administrator rights, which the session that wrote this script
# did not have (verified: registering an S4U principal or an AtStartup trigger both
# failed with "Access is denied", and HKLM\...\WindowsUpdate is not writable).
# So this is packaged as one reviewable script for the operator to run once.
#
# Background: 2026-07-31 11:30 JST a Windows Update planned reboot killed all three MT5
# terminals. The PC came straight back up and stayed up, but EA-MT5-Watchdog never ran
# again for 54 hours because it is registered LogonType=InteractiveToken and nobody
# logged on. The whole Friday session was lost. See
# docs/forward_reports/2026-08-02_improvements.md (F-1, improvements S-5 and S-6).
#
#   S-6  (-ApplyActiveHours)   reduce how often an update reboot can happen in market hours
#   S-5  (-ApplyWatchdogS4U)   make the watchdog run even with nobody logged on
#
# Default behaviour is a DRY RUN: it prints the current state and what it would change,
# and touches nothing. Add -Apply to actually write.
#
# ASCII only - Windows PowerShell 5.1 on this PC misparses Japanese string literals in
# a BOM-less UTF-8 .ps1.

[CmdletBinding()]
param(
    [switch] $ApplyActiveHours,
    [switch] $ApplyWatchdogS4U,
    [switch] $Apply,                       # without this, everything is a dry run
    [switch] $NoSelfElevate,               # do not re-launch through UAC (for automation)
    [string] $TaskName    = 'EA-MT5-Watchdog',
    [string] $ScriptPath  = 'C:\AI\claud\project\forward_test\check_and_recover.ps1',
    # Active hours = the window Windows must NOT reboot in. Max width is 18 hours.
    # 09:00 -> 03:00 JST leaves 03:00-09:00 as the only window an update reboot may use.
    # Rationale (server time = JST-6): the SCA sleeves run range 01-09h, new entries until
    # 15h and the forced close at 20h server = 02:00 JST, so 09:00->03:00 JST covers every
    # hour in which the EA can place or close an order. 03:00-09:00 JST is the post-NY /
    # pre-Tokyo lull - the least bad six hours available under the 18-hour cap.
    # The value found on this PC was 5 -> 11, i.e. it permitted reboots for the whole
    # trading day and forbade them overnight. The 07-31 reboot fired at 11:30, twenty
    # minutes after that window ended.
    [int] $ActiveHoursStart = 9,
    [int] $ActiveHoursEnd   = 3
)

$ErrorActionPreference = 'Stop'

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-State {
    Write-Output '--- current state ---'
    $ux = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
    foreach ($n in 'ActiveHoursStart','ActiveHoursEnd') {
        $v = (Get-ItemProperty -Path $ux -Name $n -ErrorAction SilentlyContinue).$n
        Write-Output ("  {0} = {1}" -f $n, $(if ($null -eq $v) { '(unset)' } else { $v }))
    }
    try {
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        Write-Output ("  task {0}: State={1} LogonType={2} Triggers={3}" -f `
            $TaskName, $t.State, $t.Principal.LogonType, $t.Triggers.Count)
    } catch {
        Write-Output ("  task {0}: NOT FOUND" -f $TaskName)
    }
    $w = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    $aal = (Get-ItemProperty -Path $w -Name 'AutoAdminLogon' -ErrorAction SilentlyContinue).AutoAdminLogon
    Write-Output ("  AutoAdminLogon = {0}" -f $(if ($null -eq $aal) { '(unset)' } else { $aal }))
    Write-Output ''
}

if (-not (Test-Elevated)) {
    # The account here IS in BUILTIN\Administrators, but an ordinary PowerShell window
    # gets a UAC-filtered token (Medium integrity, Administrators "deny only"), so every
    # write below silently has no chance of succeeding. This happened for real on
    # 2026-08-02 18:59: the correct command line was run, the guard tripped, and the
    # run looked successful because the state dump printed normally. So rather than
    # just warning, re-launch through UAC and make the failure impossible to miss.
    if ($NoSelfElevate) {
        Write-Output ''
        Write-Output '################################################################'
        Write-Output '#  NOT ELEVATED - NOTHING WAS CHANGED                          #'
        Write-Output '################################################################'
        Show-State
        exit 1
    }

    Write-Output 'Not elevated - re-launching through UAC. Approve the prompt to continue.'
    $argList = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit',
        '-File', ('"{0}"' -f $PSCommandPath)
    )
    if ($ApplyActiveHours) { $argList += '-ApplyActiveHours' }
    if ($ApplyWatchdogS4U) { $argList += '-ApplyWatchdogS4U' }
    if ($Apply)            { $argList += '-Apply' }
    $argList += @('-ActiveHoursStart', $ActiveHoursStart, '-ActiveHoursEnd', $ActiveHoursEnd)

    try {
        # -NoExit keeps the elevated window open so the post-change checklist stays readable.
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argList -ErrorAction Stop
        Write-Output 'Elevated window launched. Read the results THERE, not in this window.'
        exit 0
    } catch {
        Write-Output ''
        Write-Output '################################################################'
        Write-Output '#  NOT ELEVATED and the UAC prompt was declined or failed.     #'
        Write-Output '#  NOTHING WAS CHANGED.                                        #'
        Write-Output '#  Open PowerShell via right-click > "Run as administrator"    #'
        Write-Output '#  and run this script again.                                  #'
        Write-Output '################################################################'
        Show-State
        exit 1
    }
}

Show-State

if (-not $Apply) {
    Write-Output 'DRY RUN (no -Apply): nothing will be written.'
}

# ---------------------------------------------------------------------------
# S-6: active hours
# ---------------------------------------------------------------------------
if ($ApplyActiveHours) {
    Write-Output ('S-6: set active hours to {0}:00 -> {1}:00 (no update reboots inside this window)' -f `
        $ActiveHoursStart, $ActiveHoursEnd)
    $span = ($ActiveHoursEnd - $ActiveHoursStart + 24) % 24
    if ($span -gt 18 -or $span -eq 0) {
        Write-Warning ('  refusing: Windows caps the active-hours window at 18 hours (requested {0})' -f $span)
    } elseif ($Apply) {
        $ux = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
        New-ItemProperty -Path $ux -Name 'ActiveHoursStart' -Value $ActiveHoursStart -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $ux -Name 'ActiveHoursEnd'   -Value $ActiveHoursEnd   -PropertyType DWord -Force | Out-Null
        # SmartActiveHoursState=0 stops Windows from silently re-deriving the window from
        # usage patterns, which would quietly undo the setting above.
        New-ItemProperty -Path $ux -Name 'SmartActiveHoursState' -Value 0 -PropertyType DWord -Force | Out-Null
        Write-Output '  applied.'
    } else {
        Write-Output ('  would write ActiveHoursStart={0} ActiveHoursEnd={1} SmartActiveHoursState=0' -f `
            $ActiveHoursStart, $ActiveHoursEnd)
    }
    Write-Output ''
}

# ---------------------------------------------------------------------------
# S-5: make the watchdog logon-independent
# ---------------------------------------------------------------------------
if ($ApplyWatchdogS4U) {
    Write-Output 'S-5: re-register the watchdog as S4U (run whether the user is logged on or not) + AtStartup trigger'
    Write-Output '  NOTE: S4U runs the task in session 0. terminal64.exe is a GUI app, so its'
    Write-Output '        recovery path MUST be re-tested after this change - see the checklist below.'

    if (-not (Test-Path $ScriptPath)) {
        Write-Warning ('  refusing: watchdog script not found at {0}' -f $ScriptPath)
    } else {
        $user = "$env:USERDOMAIN\$env:USERNAME"
        $act  = New-ScheduledTaskAction -Execute 'powershell.exe' `
                    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $ScriptPath)
        # Keep the proven 30-minute cadence, and add AtStartup so a reboot is covered
        # immediately instead of waiting for the next repetition tick.
        $tRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
                    -RepetitionInterval (New-TimeSpan -Minutes 30) `
                    -RepetitionDuration (New-TimeSpan -Days 3650)
        $tBoot   = New-ScheduledTaskTrigger -AtStartup
        $set = New-ScheduledTaskSettingsSet -StartWhenAvailable `
                    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
                    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
        $set.MultipleInstances = 2   # IgnoreNew
        $prin = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Highest

        if ($Apply) {
            Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger @($tRepeat, $tBoot) `
                -Settings $set -Principal $prin `
                -Description 'EA MT5 watchdog. S4U + AtStartup so it survives an unattended reboot (S-5).' `
                -Force | Out-Null
            Write-Output '  applied.'
            Get-ScheduledTask -TaskName $TaskName |
                Select-Object TaskName, State, @{n='LogonType';e={$_.Principal.LogonType}} |
                Format-Table -AutoSize | Out-String | Write-Output
        } else {
            Write-Output ('  would re-register {0} as LogonType=S4U with triggers: 30-min repetition + AtStartup' -f $TaskName)
        }
    }
    Write-Output ''
}

Write-Output '=== POST-CHANGE CHECKLIST (S-5 acceptance: 3/3) ==='
Write-Output '1. Reboot the PC and DO NOT log on. Wait 30 minutes.'
Write-Output '2. Log on and inspect C:\AI\claud\project\forward_test\launcher_log.txt.'
Write-Output '   PASS = entries exist with timestamps from while nobody was logged on,'
Write-Output '          and all three terminals show the EA attached.'
Write-Output '3. Repeat twice more (3/3 required before declaring S-5 done).'
Write-Output ''
Write-Output 'IF STEP 2 SHOWS THE WATCHDOG RAN BUT THE TERMINALS DID NOT COME BACK:'
Write-Output '  that is the session-0 GUI limitation. Revert to LogonType=Interactive:'
Write-Output '     $p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive'
Write-Output '     Set-ScheduledTask -TaskName "EA-MT5-Watchdog" -Principal $p'
Write-Output '  and instead make a session always exist after a reboot, by enabling'
Write-Output '  Settings > Accounts > Sign-in options >'
Write-Output '    "Use my sign-in info to automatically finish setting up after an update".'
Write-Output '  That is a GUI toggle on purpose: it needs your credentials and must not be'
Write-Output '  scripted by an assistant. Do not set AutoAdminLogon with a plaintext'
Write-Output '  DefaultPassword in the registry - that stores your password in clear text.'
Write-Output ''
Write-Output 'S-7 (independent heartbeat) is already installed as scheduled task'
Write-Output '"EA-Watchdog-Heartbeat" and needs no elevation.'
