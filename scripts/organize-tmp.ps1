[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$temporaryRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.tmp'))
$comparison = [StringComparison]::OrdinalIgnoreCase
$moves = [System.Collections.Generic.List[object]]::new()

function Add-Move([string]$source, [string]$relativeTarget) {
    $destination = [IO.Path]::GetFullPath((Join-Path $temporaryRoot $relativeTarget))
    $source = [IO.Path]::GetFullPath($source)
    if (-not $source.StartsWith($temporaryRoot + '\', $comparison) -or
        -not $destination.StartsWith($temporaryRoot + '\', $comparison)) {
        throw "Move escaped the project temporary directory: $source -> $destination"
    }
    if (Test-Path -LiteralPath $destination) {
        throw "Destination already exists: $destination"
    }
    $parent = [IO.Path]::GetDirectoryName($destination)
    while ($parent.StartsWith($temporaryRoot, $comparison)) {
        if (Test-Path -LiteralPath $parent) {
            $parentItem = Get-Item -LiteralPath $parent -Force
            if (($parentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Destination parent is a reparse point: $parent"
            }
        }
        if ($parent.Equals($temporaryRoot, $comparison)) { break }
        $parent = [IO.Path]::GetDirectoryName($parent)
    }
    $item = Get-Item -LiteralPath $source -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to move a reparse point: $source"
    }
    if ($item.PSIsContainer) {
        try {
            $links = @(Get-ChildItem -LiteralPath $source -Recurse -Force -Attributes ReparsePoint -ErrorAction Stop)
        } catch [System.UnauthorizedAccessException] {
            Write-Warning "Skipping an unreadable directory: $source"
            return
        }
        if ($links.Count -gt 0) { throw "Directory contains reparse points: $source" }
    }
    $moves.Add([pscustomobject]@{ Source = $source; Destination = $destination })
}

if (-not (Test-Path -LiteralPath $temporaryRoot -PathType Container)) {
    Write-Output 'No .tmp directory exists.'
    return
}
if (((Get-Item -LiteralPath $temporaryRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'The project temporary directory is a reparse point.'
}

foreach ($file in Get-ChildItem -LiteralPath $temporaryRoot -File -Force) {
    if ($file.Extension -eq '.png') {
        Add-Move $file.FullName (Join-Path 'artifacts/screenshots' $file.Name)
    } elseif ($file.Extension -in @('.py', '.mjs', '.ps1')) {
        Add-Move $file.FullName (Join-Path 'workbench/helpers' $file.Name)
    } elseif ($file.Name -eq 'frag-archify-svg-runtime-docs-20260927.json') {
        Add-Move $file.FullName (Join-Path 'workbench/handoffs' $file.Name)
    } elseif ($file.Name -eq 'visual-plugin.zip') {
        Add-Move $file.FullName (Join-Path 'workbench/packages' $file.Name)
    }
}

foreach ($directory in Get-ChildItem -LiteralPath $temporaryRoot -Directory -Force) {
    if ($directory.Name -eq 'archify-visual-evidence') {
        Add-Move $directory.FullName 'artifacts/archify/visual-evidence'
    } elseif ($directory.Name -eq 'archify-svg-qa') {
        Add-Move $directory.FullName 'artifacts/archify/svg-qa'
    } elseif ($directory.Name -like 'pytest-*' -or $directory.Name -eq 'fc-plugin-adapter-pycache-20260927') {
        Add-Move $directory.FullName (Join-Path 'artifacts/test-runs' $directory.Name)
    } elseif ($directory.Name -in @('plugin-browser', 'plugin-browser-final', 'plugin-visual', 'visual-sources')) {
        Add-Move $directory.FullName (Join-Path 'workbench/fixtures' $directory.Name)
    }
}

if ($moves.Count -eq 0) {
    Write-Output 'No recognized root-level scratch items need organizing.'
    return
}
foreach ($move in $moves) {
    $relativeSource = $move.Source.Substring($projectRoot.Length + 1)
    $relativeDestination = $move.Destination.Substring($projectRoot.Length + 1)
    Write-Output "$relativeSource -> $relativeDestination"
}
if (-not $Apply) {
    Write-Output "Preview only: $($moves.Count) moves. Re-run with -Apply to organize them."
    return
}

foreach ($move in $moves) {
    $parent = Split-Path -Path $move.Destination -Parent
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Move-Item -LiteralPath $move.Source -Destination $move.Destination -ErrorAction Stop
}
Write-Output "Organized $($moves.Count) items without deleting files."
