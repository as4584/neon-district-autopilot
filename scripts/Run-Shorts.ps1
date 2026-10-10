param(
  [string]$Id,
  [switch]$DryRun,
  [switch]$PreviewOnly,
  [switch]$ApprovePreview,
  [switch]$Status,
  [switch]$SkipAceStepStart
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = "python"
if (Test-Path $VenvPython) {
  & $VenvPython -c "import requests" 2>$null
  if ($LASTEXITCODE -eq 0) {
    $Python = $VenvPython
  }
}

if ($Status) {
  & $Python (Join-Path $Root "yt_shorts.py") --status
  exit $LASTEXITCODE
}

$argsList = @((Join-Path $Root "yt_shorts.py"))
if ($Id) {
  $argsList += @("--id", $Id)
}
if ($DryRun) {
  $argsList += "--dry-run"
}
if ($PreviewOnly) {
  $argsList += "--preview-only"
}
if ($ApprovePreview) {
  $argsList += "--approve-preview"
}

if ($DryRun -or $ApprovePreview) {
  & $Python @argsList
  exit $LASTEXITCODE
}

if (-not $env:DOPPLER_TOKEN) {
  throw "DOPPLER_TOKEN is not set. Set your personal Doppler token before uploading Shorts."
}

$ShouldStopAceStep = -not $SkipAceStepStart
$ExitCode = 0
try {
  if ($ShouldStopAceStep) {
    & (Join-Path $PSScriptRoot "Start-AceStep.ps1")
  }

  & $Python (Join-Path $PSScriptRoot "doppler_env.py") --project agentop --config prd -- $Python @argsList
  $ExitCode = $LASTEXITCODE
} finally {
  if ($ShouldStopAceStep) {
    & (Join-Path $PSScriptRoot "Stop-AceStep.ps1") | Out-Host
  }
}
exit $ExitCode
