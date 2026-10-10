param([switch]$Enable)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Name = 'NeonDistrict-Daily-YouTube'
$Existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if ($Existing) {
  throw 'Daily task already exists. Inspect it before updating; no replacement performed.'
}
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $Root -Argument (
  '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $PSScriptRoot 'Run-DailyAutopost.ps1')
)
$Trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 8) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Local ACE-Step + FLUX daily chill/rest YouTube upload. No cloud image generation or paid coding-model dispatch. Requires signed-in user.'
$Task.Settings.Enabled = [bool]$Enable
Register-ScheduledTask -TaskName $Name -InputObject $Task | Select-Object TaskName, State
