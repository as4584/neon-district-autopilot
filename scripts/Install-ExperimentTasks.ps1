param([switch]$Enable)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Definitions = @(
  @{ Name = 'NeonDistrict-Weekly-Model-Staging'; Day = 'Thursday'; Time = '02:00'; Script = 'Run-ModelMaintenance.ps1'; Extra = '' },
  @{ Name = 'NeonDistrict-Weekly-Findings'; Day = 'Sunday'; Time = '17:00'; Script = 'Run-ExperimentReport.ps1'; Extra = ' -Publish' }
)
foreach ($Definition in $Definitions) {
  if (Get-ScheduledTask -TaskName $Definition.Name -ErrorAction SilentlyContinue) {
    throw "Task already exists; inspect before replacing: $($Definition.Name)"
  }
}
foreach ($Definition in $Definitions) {
  $Argument = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"{1}' -f (Join-Path $PSScriptRoot $Definition.Script), $Definition.Extra
  $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $Root -Argument $Argument
  $Trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek $Definition.Day -At $Definition.Time
  $Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
  $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12)
  $Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Curated local model staging or sanitized findings. No live upload and no paid coding-model dispatch.'
  $Task.Settings.Enabled = [bool]$Enable
  Register-ScheduledTask -TaskName $Definition.Name -InputObject $Task | Select-Object TaskName, State
}
