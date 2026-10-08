[CmdletBinding()]
param(
    [switch]$Apply, [string]$NewRun, [string]$CloseRun, [switch]$Disposable,
    [ValidateRange(0, 2147483647)][int]$OwnerProcessId = 0,
    [ValidateRange(1, 3650)][int]$RetentionDays = 14,
    [ValidateRange(1, 10240)][int]$MaxEvidenceMiB = 300,
    [ValidateRange(1, 365)][int]$PressureMinAgeDays = 2,
    [ValidateRange(1, 10240)][int]$MaxTotalMiB = 2048
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$temporaryRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '.tmp'))
$runsRoot = Join-Path $temporaryRoot 'runs'
$comparison = [StringComparison]::OrdinalIgnoreCase
$namePattern = '^\d{8}-\d{4}\+0800-[a-z][a-z0-9-]*-\d{2,}$'
$now = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
if (@(@($NewRun, $CloseRun, $(if ($Apply) { 'apply' })) | Where-Object { $_ }).Count -gt 1) { throw 'Choose one operation.' }

function Assert-Path([string]$target) {
    $target = [IO.Path]::GetFullPath($target)
    if (!$target.Equals($temporaryRoot, $comparison) -and !$target.StartsWith($temporaryRoot + '\', $comparison)) { throw 'Path escaped the temporary root.' }
    $ancestor = $target
    while ($ancestor -and $ancestor.StartsWith($temporaryRoot, $comparison)) {
        if (Test-Path -LiteralPath $ancestor) {
            if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked temporary paths are not allowed.' }
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    return $target
}
function Read-Tree([string]$root) {
    $files = [Collections.Generic.List[IO.FileInfo]]::new()
    $dirs = [Collections.Generic.List[IO.DirectoryInfo]]::new()
    $blocked = [Collections.Generic.List[string]]::new()
    $links = [Collections.Generic.List[string]]::new()
    $stack = [Collections.Generic.Stack[string]]::new()
    if (Test-Path -LiteralPath $root) { $stack.Push((Assert-Path $root)) }
    while ($stack.Count) {
        $directory = $stack.Pop()
        try { $entries = @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop) }
        catch { $blocked.Add($directory); continue }
        foreach ($entry in $entries) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { $links.Add($entry.FullName); continue }
            if ($entry.PSIsContainer) { $dirs.Add($entry); $stack.Push($entry.FullName) }
            else { $files.Add($entry) }
        }
    }
    $bytes = [long]0
    foreach ($file in $files) { $bytes += $file.Length }
    return [pscustomobject]@{files=@($files.ToArray()); dirs=@($dirs.ToArray()); blocked=@($blocked.ToArray()); links=@($links.ToArray()); bytes=$bytes}
}
if ($CloseRun) {
    $target = Assert-Path $CloseRun
    if (![IO.Path]::GetDirectoryName($target).Equals($runsRoot, $comparison) -or [IO.Path]::GetFileName($target) -notmatch $namePattern) { throw 'CloseRun requires a named task directly under .tmp/runs.' }
    $manifestPath = Assert-Path (Join-Path $target 'run.json')
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $manifest.status = 'closed'
    $manifest | Add-Member -NotePropertyName closedAt -NotePropertyValue $now.ToString('o') -Force
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8
    return
}
$inventory = Read-Tree $temporaryRoot
if ($NewRun) {
    if ($NewRun -notmatch '^[a-z][a-z0-9-]{1,47}$') { throw 'Purpose must be a short lowercase kebab-case identifier.' }
    if ($inventory.bytes -ge ([long]$MaxTotalMiB * 1MB)) { throw 'Temporary storage exceeds its ceiling. Clean eligible work before creating another run.' }
    if ($inventory.blocked.Count -or $inventory.links.Count) { [Console]::Error.WriteLine('Temporary size is a lower bound: unreadable or linked legacy paths are protected.') }
    $null = Assert-Path $runsRoot
    $null = New-Item -ItemType Directory -Path $runsRoot -Force
    $stem = $now.ToString('yyyyMMdd-HHmm') + '+0800-' + $NewRun
    for ($sequence = 1; $sequence -le 9999; $sequence++) {
        $target = Assert-Path (Join-Path $runsRoot ('{0}-{1:D2}' -f $stem, $sequence))
        try { $null = New-Item -ItemType Directory -Path $target -ErrorAction Stop; break }
        catch { if (!(Test-Path -LiteralPath $target -PathType Container)) { throw } }
    }
    if ($sequence -gt 9999) { throw 'Minute collision limit reached.' }
    @{purpose=$NewRun; createdAt=$now.ToString('o'); status='active'; disposable=[bool]$Disposable;
      ownerProcessId=$(if ($OwnerProcessId) { $OwnerProcessId } else { $PID })} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target 'run.json') -Encoding utf8
    Write-Output $target
    return
}
$allowedRoots = @('runs','evidence','packages','agents-dist','uv-cache','npm-cache','plugin-uploads','artifacts')
$namingWarnings = @()
if (Test-Path -LiteralPath $temporaryRoot) {
    $namingWarnings = @(Get-ChildItem -LiteralPath $temporaryRoot -Force | Where-Object { $_.Name -notin $allowedRoots } | Select-Object -ExpandProperty Name)
}
$evidenceRoot = Join-Path $temporaryRoot 'evidence'
if (Test-Path -LiteralPath $evidenceRoot) {
    $null = Assert-Path $evidenceRoot
    $namingWarnings += @(Get-ChildItem -LiteralPath $evidenceRoot -Force | Where-Object { !$_.PSIsContainer -or $_.Name -notmatch $namePattern } | ForEach-Object { 'evidence/' + $_.Name })
}
$tasks = @()
if (Test-Path -LiteralPath $runsRoot) {
    $null = Assert-Path $runsRoot
    foreach ($directory in Get-ChildItem -LiteralPath $runsRoot -Directory -Force) {
        if ($directory.Name -notmatch $namePattern) { $namingWarnings += 'runs/' + $directory.Name; continue }
        try {
            $manifestPath = Assert-Path (Join-Path $directory.FullName 'run.json')
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            # PowerShell 7.5 deserializes ISO JSON dates; older releases retain strings.
            if ($manifest.createdAt -is [DateTime]) { $created = [DateTimeOffset]$manifest.createdAt }
            elseif ($manifest.createdAt -is [string]) { $created = [DateTimeOffset]::ParseExact($manifest.createdAt, 'o', [Globalization.CultureInfo]::InvariantCulture) }
            else { throw 'Invalid creation timestamp.' }
            if ($manifest.status -ne 'closed' -or $manifest.disposable -isnot [bool] -or !$manifest.disposable -or
                ($manifest.ownerProcessId -isnot [long] -and $manifest.ownerProcessId -isnot [int]) -or $manifest.ownerProcessId -le 0) { continue }
            if (Get-Process -Id $manifest.ownerProcessId -ErrorAction SilentlyContinue) { continue }
            $tree = Read-Tree $directory.FullName
            if ($tree.blocked.Count -or $tree.links.Count) { continue }
            $tasks += [pscustomobject]@{path=$directory.FullName; tree=$tree; ageDays=($now-$created).TotalDays;
                manifestPath=$manifestPath; manifestHash=(Get-FileHash -LiteralPath $manifestPath).Hash; ownerProcessId=$manifest.ownerProcessId}
        } catch { $namingWarnings += 'unclassified:' + $directory.Name }
    }
}
$disposableBytes = [long]0
foreach ($task in $tasks) { $disposableBytes += $task.tree.bytes }
$candidates = @($tasks | Where-Object { $_.ageDays -ge $RetentionDays -or ($disposableBytes -gt ([long]$MaxEvidenceMiB*1MB) -and $_.ageDays -ge $PressureMinAgeDays) })
$deletedFiles = 0; $deletedBytes = [long]0; $failures = @()
if ($Apply) {
    foreach ($task in $candidates) {
        try {
            $null = Assert-Path $task.path
            if ((Get-FileHash -LiteralPath $task.manifestPath).Hash -ne $task.manifestHash -or (Get-Process -Id $task.ownerProcessId -ErrorAction SilentlyContinue)) { throw 'Run changed or its owner is active.' }
            # Keep the manifest until last, so an interrupted batch remains classified.
            foreach ($file in ($task.tree.files | Sort-Object { $_.FullName -eq $task.manifestPath })) {
                $target = Assert-Path $file.FullName
                $current = Get-Item -LiteralPath $target -Force
                if ($current.PSIsContainer -or $current.Length -ne $file.Length -or $current.LastWriteTimeUtc -ne $file.LastWriteTimeUtc) { throw 'File changed after inventory.' }
                Remove-Item -LiteralPath $target -Force -ErrorAction Stop
                $deletedFiles++; $deletedBytes += $file.Length
            }
            foreach ($directory in ($task.tree.dirs | Sort-Object { $_.FullName.Length } -Descending)) {
                $null = Assert-Path $directory.FullName
                [IO.Directory]::Delete($directory.FullName, $false)
            }
            $null = Assert-Path $task.path
            [IO.Directory]::Delete($task.path, $false)
        } catch { $failures += @{run=[IO.Path]::GetFileName($task.path); reason=$_.Exception.Message} }
    }
}
[ordered]@{mode=$(if ($Apply) {'apply'} else {'inventory'}); readableMiB=[math]::Round($inventory.bytes/1MB,2);
    maxTotalMiB=$MaxTotalMiB; totalIsLowerBound=[bool]($inventory.blocked.Count -or $inventory.links.Count);
    aboveCeiling=($inventory.bytes -ge ([long]$MaxTotalMiB*1MB)); unreadablePaths=$inventory.blocked; linkedPaths=$inventory.links;
    namingWarnings=$namingWarnings; eligibleRuns=@($candidates | ForEach-Object { [IO.Path]::GetFileName($_.path) });
    deletedFiles=$deletedFiles; deletedBytes=$deletedBytes; failures=$failures} | ConvertTo-Json -Depth 4
if ($failures.Count) { exit 1 }
