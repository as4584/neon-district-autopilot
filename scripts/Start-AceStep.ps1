param(
  [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$AceRoot = if ($env:NEON_ACE_STEP_ROOT) { $env:NEON_ACE_STEP_ROOT } else { Join-Path (Split-Path -Parent $Root) 'ACE-Step-1.5' }
$LogDir = Join-Path $Root 'logs'
$LogFile = Join-Path $LogDir "ace-step-api.log"
New-Item -ItemType Directory -Force $LogDir | Out-Null

function Test-AceStep {
  try {
    Invoke-WebRequest -Uri "http://127.0.0.1:8001/docs" -UseBasicParsing -TimeoutSec 3 | Out-Null
    return $true
  } catch {
    return $false
  }
}

if (Test-AceStep) {
  Write-Host "ACE-Step API is already running at http://127.0.0.1:8001"
  exit 0
}

if (-not (Test-Path $AceRoot)) {
  throw "ACE-Step folder not found: $AceRoot"
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
  $uvLocal = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
  if (Test-Path $uvLocal) {
    $env:PATH = "$(Split-Path $uvLocal);$env:PATH"
  } else {
    Write-Host "uv is missing; running ACE-Step's Windows installer."
    & (Join-Path $AceRoot "install_uv.bat") --silent
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links;$env:PATH"
  }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv is still unavailable after install attempt."
}

if (-not (Test-Path (Join-Path $AceRoot ".venv"))) {
  Write-Host "ACE-Step .venv not found; running uv sync. First run can take a while."
  Push-Location $AceRoot
  try {
    uv sync
  } finally {
    Pop-Location
  }
}

$command = @"
Set-Location '$AceRoot'
uv run --no-sync acestep-api --host 127.0.0.1 --port 8001 *> '$LogFile'
"@

Write-Host "Starting ACE-Step API..."
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 5
  if (Test-AceStep) {
    Write-Host "ACE-Step API is ready at http://127.0.0.1:8001"
    exit 0
  }
}

Write-Host "ACE-Step API did not become ready. Last log lines:"
if (Test-Path $LogFile) {
  Get-Content $LogFile -Tail 40
}
exit 1
