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
& $Python (Join-Path $Root "yt_viral_score.py") @args
exit $LASTEXITCODE
