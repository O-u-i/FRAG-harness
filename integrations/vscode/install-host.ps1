[CmdletBinding()]
param([string]$InstallPath = (Join-Path $env:LOCALAPPDATA 'FRAG\host\1.10.3'))
$ErrorActionPreference = 'Stop'
$bundleRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$hostTarget = [IO.Path]::GetFullPath($InstallPath)
if (Test-Path -LiteralPath $hostTarget) { throw 'Choose a new installation directory; existing installations are never overwritten.' }
if ($hostTarget.StartsWith($bundleRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $hostTarget -eq $bundleRoot) {
    throw 'Installation must be outside the extracted bundle.'
}
# This script belongs to the generated bundle. Do not run it directly from a source checkout.
if (!(Test-Path -LiteralPath (Join-Path $bundleRoot 'resources\dist\index.html'))) { throw 'Run install-host.ps1 from an extracted Host bundle.' }
New-Item -ItemType Directory -Path $hostTarget | Out-Null
foreach ($file in Get-ChildItem -LiteralPath $bundleRoot -File -Recurse) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked bundle entries are not allowed.' }
    $relative = [IO.Path]::GetRelativePath($bundleRoot, $file.FullName)
    if ($relative -eq 'install-host.ps1') { continue }
    if (!($relative.StartsWith('backend\frag_api\') -or $relative -in @('backend\pyproject.toml', 'backend\uv.lock') -or $relative.StartsWith('resources\'))) {
        throw 'Unexpected bundle content.'
    }
    $destination = Join-Path $hostTarget $relative
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($destination)) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination
}
& uv sync --frozen --no-dev --no-install-project --link-mode copy --python 3.12 --project (Join-Path $hostTarget 'backend')
if ($LASTEXITCODE -ne 0) { throw 'Locked environment initialization failed. Installation was retained for inspection.' }
Write-Output "Host installed: $hostTarget"
Write-Output 'Install the matching FRAG VSIX, then run FRAG: Enable in Agents Window and FRAG: Start Project Host.'
