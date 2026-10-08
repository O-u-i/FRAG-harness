[CmdletBinding()]
param([switch]$Apply)
# Compatibility entry point: old category moves would recreate the retired layout.
Write-Output 'Use scripts/maintain-tmp.ps1 -NewRun <purpose> for timestamped task directories.'
Write-Output 'Use scripts/maintain-tmp.ps1 -Apply for eligible closed-run cleanup; no legacy moves were performed.'
