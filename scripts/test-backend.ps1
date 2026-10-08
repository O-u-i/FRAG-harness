param([Parameter(ValueFromRemainingArguments=$true)][string[]]$TestArguments)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$maintenance = Join-Path $PSScriptRoot 'maintain-tmp.ps1'
$run = & $maintenance -NewRun backend-tests -Disposable -OwnerProcessId $PID
$testExit = 1
try {
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & uv run --offline --no-sync --project . --cache-dir (Join-Path $projectRoot '.tmp/uv-cache') pytest -p no:cacheprovider --basetemp (Join-Path $run 'pytest') @TestArguments
        $testExit = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    & $maintenance -CloseRun $run
    Write-Host "Backend test artifacts: $run"
}
exit $testExit
