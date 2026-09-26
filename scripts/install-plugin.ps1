param(
    [Parameter(ParameterSetName='Release', Mandatory=$true)][string]$ReleaseUrl,
    [Parameter(ParameterSetName='Local', Mandatory=$true)][string]$ArchivePath,
    [Parameter(ParameterSetName='Release', Mandatory=$true)]
    [Parameter(ParameterSetName='Local', Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    [Parameter(ParameterSetName='Disable', Mandatory=$true)][switch]$Disable,
    [string]$InstallRoot
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$installBase = if ($InstallRoot) { [System.IO.Path]::GetFullPath($InstallRoot) } else { Join-Path $projectRoot '.local-plugins' }
if ($installBase -ne $projectRoot -and -not $installBase.StartsWith($projectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'InstallRoot must stay within the FRAG repository.'
}
$pluginRoot = Join-Path $installBase 'finance-core'
$currentPath = Join-Path $pluginRoot 'current.json'

function Get-Sha256([string]$path) {
    $stream = [System.IO.File]::OpenRead($path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose(); $stream.Dispose() }
}

if ($Disable) {
    if (-not (Test-Path -LiteralPath $currentPath -PathType Leaf)) { throw 'Finance Core is not installed.' }
    $current = Get-Content -LiteralPath $currentPath -Raw | ConvertFrom-Json
    $current.enabled = $false
    $pending = Join-Path $pluginRoot 'current.pending.json'
    $current | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $pending -Encoding utf8
    Move-Item -LiteralPath $pending -Destination $currentPath -Force
    Write-Output 'Finance Core plugin disabled. Restart FRAG-harness.'
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'Release') {
    $uri = [Uri]$ReleaseUrl
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com')) {
        throw 'ReleaseUrl must be an HTTPS GitHub release asset.'
    }
    $downloadPath = Join-Path $projectRoot '.tmp\finance-core-download.zip'
    New-Item -ItemType Directory -Path (Split-Path $downloadPath) -Force | Out-Null
    Invoke-WebRequest -Uri $uri -OutFile $downloadPath -MaximumRedirection 5
    $archive = $downloadPath
} else {
    $archive = (Resolve-Path -LiteralPath $ArchivePath).Path
}

$actualHash = Get-Sha256 $archive
if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Archive SHA-256 does not match the pinned value.' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName })
    if ($names.Count -ne 3 -or @($names | Where-Object { $_ -notin @('manifest.json', 'adapter.py', 'ui.js') }).Count -ne 0) {
        throw 'Archive must contain only manifest.json, adapter.py, and ui.js at its root.'
    }
    $manifestEntry = $zip.GetEntry('manifest.json')
    $reader = [System.IO.StreamReader]::new($manifestEntry.Open())
    try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($manifest.id -ne 'finance-core' -or $manifest.protocolVersion -ne 1 -or $manifest.minHostVersion -ne '1.0.0' -or
        $manifest.fcApiVersion -ne '3.1.1' -or
        $manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Plugin manifest is incompatible with FRAG-harness v1.0.0.' }
    $fileNames = @($manifest.files.PSObject.Properties.Name)
    if ($fileNames.Count -ne 2 -or @($fileNames | Where-Object { $_ -notin @('adapter.py', 'ui.js') }).Count -ne 0) {
        throw 'Manifest must hash exactly adapter.py and ui.js.'
    }
    foreach ($name in @('adapter.py', 'ui.js')) {
        $expected = $manifest.files.$name
        if ($expected -notmatch '^[a-fA-F0-9]{64}$') { throw "Missing file hash for $name." }
        $stream = $zip.GetEntry($name).Open()
        try {
            $hasher = [System.Security.Cryptography.SHA256]::Create()
            try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
            finally { $hasher.Dispose() }
        } finally { $stream.Dispose() }
        if ($actual -ne $expected.ToLowerInvariant()) { throw "File hash mismatch for $name." }
    }
    $versionDir = Join-Path $pluginRoot "versions\$($manifest.version)"
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
Write-Output "Finance Core plugin v$($manifest.version) installed. Restart FRAG-harness."
