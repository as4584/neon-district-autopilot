param(
  [int]$LongFormMaxAgeHours = 36,
  [int]$ShortsMaxAgeHours = 96,
  [int]$FailureBlockHours = 2,
  [switch]$Json
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Now = Get-Date
$Issues = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Read-JsonFile($Path) {
  if (-not (Test-Path $Path)) {
    $Issues.Add("Missing file: $Path")
    return $null
  }
  try {
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  } catch {
    $Issues.Add("Invalid JSON: $Path - $($_.Exception.Message)")
    return $null
  }
}

function Check-Queue($Name, $Path) {
  $queue = Read-JsonFile $Path
  if (-not $queue) { return $null }
  $items = @($queue.queue)
  $generating = @($items | Where-Object { $_.status -eq "generating" })
  if ($generating.Count -gt 0) {
    $ids = ($generating | ForEach-Object { $_.id }) -join ", "
    $Issues.Add("$Name queue has stuck generating item(s): $ids")
  }
  return [pscustomobject]@{
    Name = $Name
    Total = $items.Count
    Pending = @($items | Where-Object { $_.status -eq "pending" }).Count
    Uploaded = @($items | Where-Object { $_.status -eq "uploaded" }).Count
    Failed = @($items | Where-Object { $_.status -eq "failed" }).Count
    Generating = $generating.Count
    UploadedIds = @($items | Where-Object { $_.status -eq "uploaded" } | ForEach-Object { $_.id })
  }
}

function Get-LogLineUtcTime($Line) {
  if ($Line -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC\]') {
    try {
      $parsed = [datetime]::ParseExact(
        $Matches[1],
        "yyyy-MM-dd HH:mm",
        [System.Globalization.CultureInfo]::InvariantCulture
      )
      return [datetime]::SpecifyKind($parsed, [System.DateTimeKind]::Utc)
    } catch {
      return $null
    }
  }
  return $null
}

function Check-Log($Name, $Path, $MaxAgeHours, [switch]$Required, [string[]]$UploadedIds = @(), [switch]$StaleAsWarning) {
  if (-not (Test-Path $Path)) {
    if ($Required) {
      $Issues.Add("$Name log missing: $Path")
    } else {
      $Warnings.Add("$Name log missing: $Path")
    }
    return $null
  }

  $file = Get-Item -LiteralPath $Path
  $ageHours = ($Now - $file.LastWriteTime).TotalHours
  if ($ageHours -gt $MaxAgeHours) {
    $staleMessage = "$Name log is stale: last update $([math]::Round($ageHours, 1))h ago"
    if ($StaleAsWarning) {
      $Warnings.Add("$staleMessage (queue complete)")
    } else {
      $Issues.Add($staleMessage)
    }
  }

  $tail = @(Get-Content -LiteralPath $Path -Tail 120 -ErrorAction SilentlyContinue)
  $latestRunIndex = -1
  for ($i = 0; $i -lt $tail.Count; $i++) {
    if ($tail[$i] -match "=== yt_.* run") {
      $latestRunIndex = $i
    }
  }
  if ($latestRunIndex -ge 0) {
    $scanLines = @($tail[$latestRunIndex..($tail.Count - 1)])
  } else {
    $scanLines = $tail
  }

  $bad = $scanLines | Where-Object {
    $isRecoveredFailure = $_ -match "FAILED: item ([^ ]+) marked failed" -and $UploadedIds -contains $Matches[1]
    $_ -match "ERROR|FAILED|Traceback|DOPPLER_TOKEN is not set|Failed to start ACE-Step|Token refresh failed" -and
    -not $isRecoveredFailure -and
    $_ -notmatch "Thumbnail generation failed.*upload continues" -and
    $_ -notmatch "Thumbnail generation failed.*falling back"
  }
  if ($bad.Count -gt 0) {
    $latestBad = $bad[-1]
    $latestBadTime = $null
    for ($i = $bad.Count - 1; $i -ge 0; $i--) {
      $latestBadTime = Get-LogLineUtcTime $bad[$i]
      if ($latestBadTime) { break }
    }
    if (-not $latestBadTime) {
      $latestBadTime = $file.LastWriteTime.ToUniversalTime()
    }

    $badAgeHours = ($Now.ToUniversalTime() - $latestBadTime).TotalHours
    $badAge = [math]::Round($badAgeHours, 2)
    if ($badAgeHours -le $FailureBlockHours) {
      $Issues.Add("$Name log contains fresh failure text (${badAge}h ago): $latestBad")
    } else {
      $Warnings.Add("$Name log contains older failure text (${badAge}h ago): $latestBad")
    }
  }

  return [pscustomobject]@{
    Name = $Name
    Path = $Path
    LastWriteTime = $file.LastWriteTime
    AgeHours = [math]::Round($ageHours, 2)
  }
}

$longQueue = Check-Queue "Long-form" (Join-Path $Root "yt_queue.json")
$shortsQueue = Check-Queue "Shorts" (Join-Path $Root "shorts_queue.json")

$autopostLog = Check-Log "Autopost" (Join-Path $Root "test_outputs\autopost.log") $LongFormMaxAgeHours -Required -UploadedIds @($longQueue.UploadedIds)
$shortsQueueComplete = $shortsQueue -and $shortsQueue.Pending -eq 0 -and $shortsQueue.Generating -eq 0 -and $shortsQueue.Failed -eq 0
$shortsLog = Check-Log "Shorts" (Join-Path $Root "test_outputs\shorts.log") $ShortsMaxAgeHours -StaleAsWarning:$shortsQueueComplete

if (-not $env:DOPPLER_TOKEN) {
  $Issues.Add("DOPPLER_TOKEN is not set in this environment")
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$QaPython = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
& $QaPython -c "import requests, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
  $Issues.Add("Python visual QA dependencies are missing; run scripts\Setup-NeonAutopost.ps1")
}

$ImagePython = if ($env:LOCAL_IMAGE_PYTHON) { $env:LOCAL_IMAGE_PYTHON } else { Join-Path $Root ".venv-images\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $ImagePython)) {
  $Issues.Add("Local image environment is not installed; see LOCAL_IMAGE_MIGRATION.md")
} else {
  & $ImagePython (Join-Path $PSScriptRoot 'generate_local_image.py') --check-ready 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { $Issues.Add('Local image dependencies, CUDA, or cached weights are not ready') }
}

$qaDiscovery = & $QaPython (Join-Path $Root "yt_visual_qa.py") --check-model 2>$null
if ($LASTEXITCODE -ne 0) {
  $Issues.Add("Ollama visual QA unavailable: $qaDiscovery")
}

$summary = [pscustomobject]@{
  ok = ($Issues.Count -eq 0)
  checked_at = (Get-Date).ToString("o")
  visual_qa_model = $qaDiscovery
  issues = @($Issues)
  warnings = @($Warnings)
  queues = @($longQueue, $shortsQueue) | Where-Object { $_ -ne $null }
  logs = @($autopostLog, $shortsLog) | Where-Object { $_ -ne $null }
}

if ($Json) {
  $summary | ConvertTo-Json -Depth 6
} else {
  Write-Host "=== Neon District Health Check ==="
  foreach ($q in $summary.queues) {
    Write-Host ("{0}: pending={1} uploaded={2} failed={3} generating={4}" -f $q.Name, $q.Pending, $q.Uploaded, $q.Failed, $q.Generating)
  }
  foreach ($log in $summary.logs) {
    Write-Host ("{0} log age: {1}h" -f $log.Name, $log.AgeHours)
  }
  foreach ($warning in $Warnings) {
    Write-Host "WARNING: $warning"
  }
  if ($Issues.Count -eq 0) {
    Write-Host "OK: no silent-failure conditions detected."
  } else {
    Write-Host "FAIL:"
    foreach ($issue in $Issues) {
      Write-Host "  - $issue"
    }
  }
}

if ($Issues.Count -gt 0) {
  exit 1
}
exit 0
