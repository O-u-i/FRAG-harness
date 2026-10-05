param(
    [Parameter(ParameterSetName='Release', Mandatory=$true)][string]$ReleaseUrl,
    [Parameter(ParameterSetName='Local', Mandatory=$true)][string]$ArchivePath,
    [Parameter(ParameterSetName='Release', Mandatory=$true)]
    [Parameter(ParameterSetName='Local', Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    [Parameter(ParameterSetName='Disable', Mandatory=$true)][switch]$Disable,
    [Parameter(ParameterSetName='Enable', Mandatory=$true)][switch]$Enable,
    [Parameter(ParameterSetName='Uninstall', Mandatory=$true)][switch]$Uninstall,
    [ValidatePattern('^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')][ValidateLength(1,63)][string]$PluginId = 'finance-core',
    [string]$InstallRoot
)

$ErrorActionPreference = 'Stop'
if ($PluginId -cnotmatch '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$') { throw 'Plugin ID must be a lowercase safe slug.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$installBase = if ($InstallRoot) { [System.IO.Path]::GetFullPath($InstallRoot) } else { Join-Path $projectRoot '.local-plugins' }
if ($installBase -ne $projectRoot -and -not $installBase.StartsWith($projectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'InstallRoot must stay within the FRAG repository.'
}
function Assert-NoReparsePoint([string]$path) {
    $candidate = $path
    while ($candidate -ne $projectRoot) {
        if (Test-Path -LiteralPath $candidate) {
            $item = Get-Item -LiteralPath $candidate -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw 'Plugin installation path cannot contain a junction or symbolic link.'
            }
        }
        $candidate = Split-Path -Path $candidate -Parent
    }
}
if ($Uninstall) {
    throw "Manual removal required: disable $PluginId, stop FRAG, and manually remove its directory under the configured InstallRoot. No files were deleted."
}

function Get-Sha256([string]$path) {
    $stream = [System.IO.File]::OpenRead($path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose(); $stream.Dispose() }
}

if ($Disable -or $Enable) {
    $pluginRoot = Join-Path $installBase $PluginId
    Assert-NoReparsePoint $pluginRoot
    $currentPath = Join-Path $pluginRoot 'current.json'
    Assert-NoReparsePoint $currentPath
    if (-not (Test-Path -LiteralPath $currentPath -PathType Leaf)) { throw 'Plugin is not installed.' }
    $current = Get-Content -LiteralPath $currentPath -Raw | ConvertFrom-Json
    if ($current.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Installed plugin version is invalid.' }
    $current.enabled = [bool]$Enable
    $pending = Join-Path $pluginRoot 'current.pending.json'
    $current | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $pending -Encoding utf8
    Move-Item -LiteralPath $pending -Destination $currentPath -Force
    $action = if ($Enable) { 'enabled' } else { 'disabled' }
    Write-Output "Plugin $PluginId $action. Restart FRAG-harness."
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'Release') {
    $uri = [Uri]$ReleaseUrl
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com')) {
        throw 'ReleaseUrl must be an HTTPS GitHub release asset.'
    }
    $downloadPath = Join-Path $projectRoot '.tmp\plugin-download.zip'
    Assert-NoReparsePoint $downloadPath
    New-Item -ItemType Directory -Path (Split-Path $downloadPath) -Force | Out-Null
    Invoke-WebRequest -Uri $uri -OutFile $downloadPath -MaximumRedirection 5
    $archive = $downloadPath
} else {
    $archive = (Resolve-Path -LiteralPath $ArchivePath).Path
}

if ((Get-Item -LiteralPath $archive).Length -gt 20MB) { throw 'Archive exceeds the 20 MiB size limit.' }
$actualHash = Get-Sha256 $archive
if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Archive SHA-256 does not match the pinned value.' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName })
    if ($names.Count -ne 3 -or @($names | Select-Object -Unique).Count -ne 3 -or @($names | Where-Object { $_ -cnotin @('manifest.json', 'adapter.py', 'ui.js') }).Count -ne 0) {
        throw 'Archive must contain only manifest.json, adapter.py, and ui.js at its root.'
    }
    $limits = @{ 'manifest.json' = 64KB; 'adapter.py' = 2MB; 'ui.js' = 5MB }
    foreach ($entry in $zip.Entries) {
        if ($entry.Length -gt $limits[$entry.FullName]) { throw "Archive entry exceeds its size limit: $($entry.FullName)" }
    }
    $manifestEntry = $zip.GetEntry('manifest.json')
    $reader = [System.IO.StreamReader]::new($manifestEntry.Open())
    try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    foreach ($field in @('id', 'protocolVersion', 'version', 'minHostVersion', 'files')) {
        if ($field -cnotin @($manifest.PSObject.Properties.Name)) { throw 'Plugin manifest fields must match the contract.' }
    }
    if ($manifest.id -isnot [string] -or $manifest.id.Length -gt 63 -or $manifest.id -cnotmatch '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$' -or
        $manifest.version -isnot [string] -or $manifest.version -notmatch '^\d+\.\d+\.\d+$' -or
        ($manifest.protocolVersion -isnot [int] -and $manifest.protocolVersion -isnot [long])) { throw 'Plugin manifest is incompatible with this FRAG host.' }
    if ($manifest.protocolVersion -eq 1) {
        if ($manifest.id -ne 'finance-core' -or $manifest.minHostVersion -ne '1.0.0' -or $manifest.fcApiVersion -ne '3.1.1') {
            throw 'Plugin manifest is incompatible with this FRAG host.'
        }
    } elseif ($manifest.protocolVersion -eq 2) {
        $allowedFields = @('id', 'name', 'protocolVersion', 'version', 'minHostVersion', 'capabilities', 'files')
        if ($manifest.id -eq 'finance-core') { $allowedFields += 'fcApiVersion' }
        $manifestFields = @($manifest.PSObject.Properties.Name)
        if ($manifestFields.Count -ne $allowedFields.Count -or @($manifestFields | Where-Object { $_ -cnotin $allowedFields }).Count -ne 0 -or
            $manifest.minHostVersion -ne '1.8.0' -or $manifest.name -isnot [string] -or -not $manifest.name -or $manifest.name.Length -gt 100 -or
            $manifest.capabilities -isnot [array] -or $manifest.capabilities.Count -ne 1 -or $manifest.capabilities[0] -cne 'evidence.read' -or
            ($manifest.id -eq 'finance-core' -and $manifest.fcApiVersion -ne '3.1.1')) {
            throw 'Plugin manifest is incompatible with this FRAG host.'
        }
    } else { throw 'Plugin protocol is unsupported.' }
    if ($PSBoundParameters.ContainsKey('PluginId') -and $PluginId -cne $manifest.id) { throw 'Plugin ID does not match the pinned archive.' }
    $PluginId = $manifest.id
    $pluginRoot = Join-Path $installBase $PluginId
    Assert-NoReparsePoint $pluginRoot
    $currentPath = Join-Path $pluginRoot 'current.json'
    $fileNames = @($manifest.files.PSObject.Properties.Name)
    if ($fileNames.Count -ne 2 -or @($fileNames | Where-Object { $_ -cnotin @('adapter.py', 'ui.js') }).Count -ne 0) {
        throw 'Manifest must hash exactly adapter.py and ui.js.'
    }
    foreach ($name in @('adapter.py', 'ui.js')) {
        $expected = $manifest.files.$name
        if ($expected -isnot [string] -or $expected -notmatch '^[a-fA-F0-9]{64}$') { throw "Missing file hash for $name." }
        $stream = $zip.GetEntry($name).Open()
        try {
            $hasher = [System.Security.Cryptography.SHA256]::Create()
            try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
            finally { $hasher.Dispose() }
        } finally { $stream.Dispose() }
        if ($actual -ne $expected.ToLowerInvariant()) { throw "File hash mismatch for $name." }
    }
    $versionDir = Join-Path $pluginRoot "versions\$($manifest.version)"
    Assert-NoReparsePoint $versionDir
    if (Test-Path -LiteralPath $versionDir) { throw 'This plugin version is already installed; use a new version.' }
    New-Item -ItemType Directory -Path $versionDir -Force | Out-Null
    foreach ($name in $names) {
        $target = Join-Path $versionDir $name
        $inputStream = $zip.GetEntry($name).Open()
        $outputStream = [System.IO.File]::Create($target)
        try { $inputStream.CopyTo($outputStream) } finally { $inputStream.Dispose(); $outputStream.Dispose() }
    }
} finally { $zip.Dispose() }

$pending = Join-Path $pluginRoot 'current.pending.json'
@{ version = $manifest.version; enabled = $true } | ConvertTo-Json | Set-Content -LiteralPath $pending -Encoding utf8
Move-Item -LiteralPath $pending -Destination $currentPath -Force
Write-Output "Plugin $PluginId v$($manifest.version) installed. Restart FRAG-harness."
