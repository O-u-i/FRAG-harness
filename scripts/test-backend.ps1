# Avoid PowerShell common-parameter binding of pytest flags such as -o and -v.
$TestArguments = $args
$ErrorActionPreference = 'Stop'
# Keep custom option values attached: before tests/conftest.py registers them,
# pytest otherwise mistakes existing archive paths for test-discovery roots.
$pytestArguments = [Collections.Generic.List[string]]::new()
for ($i = 0; $i -lt $TestArguments.Count; $i++) {
    $argument = $TestArguments[$i]
    if ($argument -in @('--fc-archive', '--legacy-host') -and $i + 1 -lt $TestArguments.Count -and !$TestArguments[$i + 1].StartsWith('-')) {
        $i++
        $argument += '=' + $TestArguments[$i]
    }
    $pytestArguments.Add($argument)
}
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$maintenance = Join-Path $PSScriptRoot 'maintain-tmp.ps1'
$run = & $maintenance -NewRun backend-tests -Disposable -OwnerProcessId $PID
$testExit = 1
try {
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & uv run --offline --no-sync --project . --cache-dir (Join-Path $projectRoot '.tmp/uv-cache') pytest -p no:cacheprovider --basetemp (Join-Path $run 'pytest') @pytestArguments
        $testExit = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    & $maintenance -CloseRun $run
    Write-Host "Backend test artifacts: $run"
}
exit $testExit
