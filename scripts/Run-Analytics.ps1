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

if (-not $env:DOPPLER_TOKEN) {
  throw "DOPPLER_TOKEN is not set. Analytics needs YouTube secrets from Doppler."
}

& $Python (Join-Path $PSScriptRoot "doppler_env.py") --project agentop --config prd -- $Python (Join-Path $Root "yt_analytics.py") @args
exit $LASTEXITCODE
