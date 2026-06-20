param(
    [int]$MaxTasks = 3,
    [string]$Branch = "autodev/egolink-p0",
    [string]$Model = "",
    [ValidateSet("low", "medium", "high", "xhigh")]
    [string]$ReasoningEffort = "medium",
    [int]$TaskTimeoutSeconds = 5400,
    [switch]$DryRun,
    [switch]$KeepFailedChanges,
    [switch]$VerboseEvents
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ArgsList = @(
    "scripts/autodev.py",
    "run",
    "--max-tasks", $MaxTasks,
    "--branch", $Branch,
    "--reasoning-effort", $ReasoningEffort,
    "--task-timeout", $TaskTimeoutSeconds
)

if ($Model) {
    $ArgsList += @("--model", $Model)
}
if ($DryRun) {
    $ArgsList += "--dry-run"
}
if ($KeepFailedChanges) {
    $ArgsList += "--keep-failed-changes"
}
if ($VerboseEvents) {
    $ArgsList += "--verbose-events"
}

Write-Host "Ego Link AutoDev" -ForegroundColor Cyan
Write-Host "Repository : $RepoRoot"
Write-Host "Max tasks : $MaxTasks"
Write-Host "Branch    : $Branch"
Write-Host ""

& python @ArgsList
exit $LASTEXITCODE
