[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateRange(1, 3650)][int]$RetentionDays = 14,
    [ValidateRange(1, 10240)][int]$MaxEvidenceMiB = 300,
    [ValidateRange(1, 365)][int]$PressureMinAgeDays = 2
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$temporaryRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.tmp'))
$evidenceRoot = [IO.Path]::GetFullPath((Join-Path $temporaryRoot 'artifacts'))
$comparison = [StringComparison]::OrdinalIgnoreCase

if (-not $temporaryRoot.StartsWith($projectRoot + '\', $comparison) -or
    -not $evidenceRoot.StartsWith($temporaryRoot + '\', $comparison)) {
    throw 'Temporary paths must remain inside this project.'
}
if (-not (Test-Path -LiteralPath $evidenceRoot -PathType Container)) {
    Write-Output 'No disposable artifact area exists; no cleanup candidate.'
    return
}

$temporaryItem = Get-Item -LiteralPath $temporaryRoot -Force
if (($temporaryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'The project temporary directory is a reparse point.'
}
$rootItem = Get-Item -LiteralPath $evidenceRoot -Force
if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'The disposable artifact area is a reparse point.'
}

$directories = [System.Collections.Generic.Stack[System.IO.DirectoryInfo]]::new()
$files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
$directories.Push($rootItem)
while ($directories.Count -gt 0) {
    $directory = $directories.Pop()
    foreach ($entry in Get-ChildItem -LiteralPath $directory.FullName -Force) {
        if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
        if ($entry.PSIsContainer) {
            $directories.Push($entry)
        } elseif ($entry -is [IO.FileInfo]) {
            $files.Add($entry)
        }
    }
}

$now = [DateTime]::UtcNow
$evidenceBytes = [long]0
foreach ($file in $files) { $evidenceBytes += $file.Length }
$limitBytes = [long]$MaxEvidenceMiB * 1MB
$overLimit = $evidenceBytes -gt $limitBytes
$candidates = foreach ($file in $files) {
    $ageDays = ($now - $file.LastWriteTimeUtc).TotalDays
    $reason = if ($ageDays -ge $RetentionDays) {
        'age'
    } elseif ($overLimit -and $ageDays -ge $PressureMinAgeDays) {
        'size pressure'
    } else {
        $null
    }
    if ($reason) {
        [pscustomobject]@{ File = $file; Reason = $reason; AgeDays = $ageDays }
    }
}
$candidate = $candidates | Sort-Object { $_.File.LastWriteTimeUtc }, { $_.File.FullName } | Select-Object -First 1
$sizeMiB = [math]::Round($evidenceBytes / 1MB, 2)
if (-not $candidate) {
    Write-Output "Disposable artifacts: $sizeMiB MiB across $($files.Count) files. No file qualifies for cleanup."
    return
}

$selectedPath = [IO.Path]::GetFullPath($candidate.File.FullName)
if (-not $selectedPath.StartsWith($evidenceRoot + '\', $comparison)) {
    throw 'The selected file escaped the disposable artifact area.'
}
$relativePath = $selectedPath.Substring($projectRoot.Length + 1)
$age = [math]::Round($candidate.AgeDays, 1)
$mode = if ($Apply) { 'APPLY' } else { 'PREVIEW' }
Write-Output "${mode}: $relativePath ($($candidate.Reason); $age days old; $sizeMiB MiB in disposable artifacts)."

if ($Apply) {
    $current = Get-Item -LiteralPath $selectedPath -Force -ErrorAction Stop
    if ($current.PSIsContainer -or
        ($current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        $current.Length -ne $candidate.File.Length -or
        $current.LastWriteTimeUtc -ne $candidate.File.LastWriteTimeUtc) {
        throw 'The selected file changed after inspection; nothing was deleted.'
    }
    Remove-Item -LiteralPath $selectedPath -Force -ErrorAction Stop
    Write-Output "Deleted one file: $relativePath"
} else {
    Write-Output 'Preview only. Re-run with -Apply to delete this one eligible file.'
}
