param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'
$updatePlan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$installPath = [IO.Path]::GetFullPath($updatePlan.install).TrimEnd('\')
$stagingPath = [IO.Path]::GetFullPath($updatePlan.staging).TrimEnd('\')
$candidatePath = [IO.Path]::GetFullPath($updatePlan.candidate).TrimEnd('\')
$backupPath = [IO.Path]::GetFullPath($updatePlan.backup).TrimEnd('\')
$parentPath = [IO.Directory]::GetParent($installPath).FullName
# All moves use literal verified absolute sibling paths. Never delete user data.
if ([IO.Directory]::GetParent($stagingPath).FullName -ne $parentPath -or
    [IO.Directory]::GetParent($backupPath).FullName -ne $parentPath -or
    -not ([IO.Path]::GetFileName($stagingPath).StartsWith('.HallAircon-update-')) -or
    -not ([IO.Path]::GetFileName($backupPath).StartsWith([IO.Path]::GetFileName($installPath) + '.previous-')) -or
    $candidatePath -ne (Join-Path $stagingPath 'payload\HallAirconStudio') -or
    $installPath -eq $parentPath -or (Test-Path -LiteralPath $backupPath)) { throw 'Invalid update paths' }
$originalMoved = $false
$replacementMoved = $false
function Write-UpdateResult($status) {
    @{status=$status; version=$updatePlan.version; backup=$backupPath} | ConvertTo-Json | Set-Content -LiteralPath $updatePlan.result -Encoding UTF8
}
function Move-WithRetry($from, $to) {
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try { Move-Item -LiteralPath $from -Destination $to; return } catch { if ($attempt -eq 29) { throw }; Start-Sleep -Milliseconds 500 }
    }
}
try {
    $parentProcess = Get-Process -Id $updatePlan.pid -ErrorAction Stop
    Set-Content -LiteralPath $updatePlan.ready -Value 'ready'
    if (-not $parentProcess.WaitForExit(90000)) { throw 'Application has not exited' }
    if (-not (Test-Path -LiteralPath (Join-Path $candidatePath 'HallAirconStudio.exe'))) { throw 'Missing executable' }
    Move-WithRetry $installPath $backupPath
    $originalMoved = $true
    Move-WithRetry $candidatePath $installPath
    $replacementMoved = $true
    Write-UpdateResult 'updated'
    Start-Process -FilePath (Join-Path $installPath 'HallAirconStudio.exe') -WorkingDirectory $installPath
} catch {
    if ($originalMoved) {
        try {
            if ($replacementMoved) { Move-WithRetry $installPath (Join-Path $stagingPath 'failed-install') }
            Move-WithRetry $backupPath $installPath
            Write-UpdateResult 'rolled_back'
            Start-Process -FilePath (Join-Path $installPath 'HallAirconStudio.exe') -WorkingDirectory $installPath
        } catch { Write-UpdateResult 'restore_required' }
    } else {
        Write-UpdateResult 'unchanged'
        if ($parentProcess -and $parentProcess.HasExited -and (Test-Path -LiteralPath (Join-Path $installPath 'HallAirconStudio.exe'))) {
            Start-Process -FilePath (Join-Path $installPath 'HallAirconStudio.exe') -WorkingDirectory $installPath
        }
    }
}
