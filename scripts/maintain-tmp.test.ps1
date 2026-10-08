$ErrorActionPreference = 'Stop'
$maintenance = Join-Path $PSScriptRoot 'maintain-tmp.ps1'
$temporaryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.tmp'))
$owned = [Collections.Generic.List[string]]::new()
function Assert-True([bool]$condition, [string]$message) { if (!$condition) { throw $message } }
function Fixture([string]$status, [object]$disposable, [int]$age, [int]$owner) {
    $run = & $maintenance -NewRun maintenance-fixture -Disposable -OwnerProcessId $owner
    $owned.Add($run)
    $manifest = Get-Content -LiteralPath (Join-Path $run 'run.json') -Raw | ConvertFrom-Json
    $manifest.createdAt = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).AddDays(-$age).ToString('o')
    $manifest.status = $status; $manifest.disposable = $disposable
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'run.json') -Encoding utf8
    Set-Content -LiteralPath (Join-Path $run 'synthetic.txt') -Value 'Synthetic temporary fixture.'
    return $run
}
try {
    $expiredOne = Fixture closed $true 15 999999
    $expiredTwo = Fixture closed $true 15 999999
    Assert-True ($expiredOne -ne $expiredTwo) 'Same-minute allocations collided.'
    Assert-True ([IO.Path]::GetFileName($expiredOne) -match '^\d{8}-\d{4}\+0800-maintenance-fixture-\d{2,}$') 'Minute/timezone naming failed.'
    $live = Fixture closed $true 15 $PID
    $active = Fixture active $true 15 999999
    $unique = Fixture closed $false 15 999999
    $malformed = Fixture closed 'true' 15 999999
    $recent = Fixture closed $true 0 999999
    $pressureOld = Fixture closed $true 3 999999
    $pressureYoung = Fixture closed $true 1 999999
    [IO.File]::WriteAllBytes((Join-Path $pressureOld 'synthetic.txt'), [byte[]]::new(1MB))
    [IO.File]::WriteAllBytes((Join-Path $pressureYoung 'synthetic.txt'), [byte[]]::new(1MB))
    $preview = & $maintenance | ConvertFrom-Json
    $expected = @($expiredOne,$expiredTwo) | ForEach-Object { [IO.Path]::GetFileName($_) }
    Assert-True ($preview.eligibleRuns.Count -eq 2 -and @($preview.eligibleRuns | Where-Object { $_ -notin $expected }).Count -eq 0) 'Cleanup did not isolate the two expired disposable runs; no unrelated run may be selected during this test.'
    $result = & $maintenance -Apply | ConvertFrom-Json
    Assert-True ($result.deletedFiles -eq 4 -and $result.failures.Count -eq 0) 'Batch cleanup failed.'
    Assert-True (!(Test-Path -LiteralPath $expiredOne) -and !(Test-Path -LiteralPath $expiredTwo)) 'Eligible runs remained.'
    foreach ($protected in @($live,$active,$unique,$malformed,$recent,$pressureOld,$pressureYoung)) {
        Assert-True (Test-Path -LiteralPath (Join-Path $protected 'synthetic.txt')) 'Protected run was removed.'
    }
    $pressure = & $maintenance -MaxEvidenceMiB 1 | ConvertFrom-Json
    Assert-True ($pressure.eligibleRuns.Count -eq 1 -and $pressure.eligibleRuns[0] -eq [IO.Path]::GetFileName($pressureOld)) 'Pressure cleanup did not enforce the two-day minimum.'
    $pressureResult = & $maintenance -Apply -MaxEvidenceMiB 1 | ConvertFrom-Json
    Assert-True ($pressureResult.deletedFiles -eq 2 -and $pressureResult.failures.Count -eq 0 -and (Test-Path -LiteralPath (Join-Path $pressureYoung 'synthetic.txt'))) 'Pressure batch removed protected recent files.'
    $outsideRejected = $false
    try { & $maintenance -CloseRun $PSScriptRoot } catch { $outsideRejected = $true }
    Assert-True $outsideRejected 'An outside path was accepted.'
    $invalidRejected = $false
    try { & $maintenance -NewRun '../outside' } catch { $invalidRejected = $true }
    Assert-True $invalidRejected 'A traversal purpose was accepted.'
    [IO.File]::WriteAllBytes((Join-Path $recent 'synthetic.txt'), [byte[]]::new(1MB))
    $capacityRejected = $false
    try { & $maintenance -NewRun capacity-test -MaxTotalMiB 1 } catch { $capacityRejected = $true }
    Assert-True $capacityRejected 'A new run bypassed the total capacity gate.'
    Write-Output 'PASS: minute/collision allocation, batch expiry and pressure age, live/active/unique/malformed/recent protection, outside-path and capacity gates.'
} finally {
    # These are this test's explicit synthetic paths, not unclassified user state.
    foreach ($run in $owned) {
        if (!$run.StartsWith($temporaryRoot + '\runs\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Test cleanup escaped its root.' }
        if (!(Test-Path -LiteralPath $run)) { continue }
        foreach ($name in @('synthetic.txt','run.json')) {
            $file = Join-Path $run $name
            if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
        }
        [IO.Directory]::Delete($run, $false)
    }
}
