$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
Push-Location $Root
try {
  & $Python (Join-Path $Root 'yt_experiments.py') --stage
  $Code = $LASTEXITCODE
} finally {
  Pop-Location
}
exit $Code
