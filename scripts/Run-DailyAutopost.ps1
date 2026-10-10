param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Log = Join-Path $Root 'test_outputs\daily-dispatch.log'
$Arguments = @((Join-Path $Root 'yt_daily.py'))
if ($PrepareOnly) { $Arguments += '--prepare-only' }
Set-Location -LiteralPath $Root
& $Python @Arguments 2>&1 | Tee-Object -FilePath $Log -Append
exit $LASTEXITCODE
