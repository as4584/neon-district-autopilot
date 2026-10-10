param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Log = Join-Path $Root 'test_outputs\daily-dispatch.log'
$Arguments = @((Join-Path $Root 'yt_daily.py'))
if ($PrepareOnly) { $Arguments += '--prepare-only' }
Set-Location -LiteralPath $Root
& $Python @Arguments 2>&1 | ForEach-Object {
  $_ | Out-File -FilePath $Log -Encoding utf8 -Append
  Write-Output $_
}
exit $LASTEXITCODE
