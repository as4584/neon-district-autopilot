$ErrorActionPreference = "SilentlyContinue"
$matches = Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -match "acestep-api" -or
      $_.CommandLine -match "acestep\.api_server"
    )
  }

if (-not $matches) {
  Write-Host "No ACE-Step API process found."
  exit 0
}

foreach ($proc in $matches) {
  Write-Host "Stopping ACE-Step process $($proc.ProcessId)"
  Stop-Process -Id $proc.ProcessId -Force
}
