param(
  [string]$Id,
  [switch]$DryRun,
  [switch]$Status,
  [switch]$SkipAceStepStart
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = "python"
if (Test-Path $VenvPython) {
  & $VenvPython -c "import requests, PIL" 2>$null
  if ($LASTEXITCODE -eq 0) {
    $Python = $VenvPython
  } else {
    throw "Existing .venv lacks visual-QA dependencies. Run scripts\Setup-NeonAutopost.ps1 to repair it."
  }
} else {
  & $Python -c "import requests, PIL" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "Python lacks visual-QA dependencies. Run scripts\Setup-NeonAutopost.ps1 first."
  }
}

if ($Status) {
  & $Python (Join-Path $Root "yt_autopost.py") --status
  exit $LASTEXITCODE
}

$argsList = @((Join-Path $Root "yt_autopost.py"))
if ($Id) {
  $argsList += @("--id", $Id)
}
if ($DryRun) {
  $argsList += "--dry-run"
}

if ($DryRun) {
  & $Python @argsList
  exit $LASTEXITCODE
}

if (-not $env:DOPPLER_TOKEN) {
  $env:DOPPLER_TOKEN = [Environment]::GetEnvironmentVariable("DOPPLER_TOKEN", "User")
  if (-not $env:DOPPLER_TOKEN) {
    $env:DOPPLER_TOKEN = [Environment]::GetEnvironmentVariable("DOPPLER_TOKEN", "Machine")
  }
  if (-not $env:DOPPLER_TOKEN) {
    throw "DOPPLER_TOKEN is not available for the scheduled user."
  }
}

$ImagePython = if ($env:LOCAL_IMAGE_PYTHON) { $env:LOCAL_IMAGE_PYTHON } else { Join-Path $Root ".venv-images\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $ImagePython)) {
  throw "Local image environment is not installed. Review LOCAL_IMAGE_MIGRATION.md before starting generation."
}
& $ImagePython (Join-Path $PSScriptRoot 'generate_local_image.py') --check-ready
if ($LASTEXITCODE -ne 0) { throw 'Local image runtime or model cache is not ready; upload blocked.' }

$queue = Get-Content -LiteralPath (Join-Path $Root "yt_queue.json") -Raw | ConvertFrom-Json
$candidate = if ($Id) { $queue.queue | Where-Object { $_.id -eq $Id -and $_.status -eq 'pending' } | Select-Object -First 1 } else { $queue.queue | Where-Object { $_.status -eq 'pending' } | Select-Object -First 1 }
$ShouldStopAceStep = $candidate -and $candidate.mode -notin @('reuse', 'stitch') -and -not $SkipAceStepStart
$ExitCode = 0
try {
  if ($ShouldStopAceStep) {
    & (Join-Path $PSScriptRoot "Start-AceStep.ps1")
    if ($LASTEXITCODE -ne 0) { throw 'ACE-Step startup failed; upload blocked.' }
  }

  & $Python (Join-Path $PSScriptRoot "doppler_env.py") --project agentop --config prd -- $Python @argsList
  $ExitCode = $LASTEXITCODE
} finally {
  if ($ShouldStopAceStep) {
    & (Join-Path $PSScriptRoot "Stop-AceStep.ps1") | Out-Host
  }
}
exit $ExitCode
