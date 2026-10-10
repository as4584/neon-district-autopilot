param([switch]$Publish)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not $env:DOPPLER_TOKEN) {
  $env:DOPPLER_TOKEN = [Environment]::GetEnvironmentVariable('DOPPLER_TOKEN', 'User')
}
if (-not $env:DOPPLER_TOKEN) { throw 'Doppler credential unavailable; report refresh blocked.' }
& $Python (Join-Path $PSScriptRoot 'doppler_env.py') --project agentop --config prd -- $Python (Join-Path $Root 'yt_experiments.py') --refresh
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Publish) {
  & $Python (Join-Path $PSScriptRoot 'publish_findings.py')
  exit $LASTEXITCODE
}
