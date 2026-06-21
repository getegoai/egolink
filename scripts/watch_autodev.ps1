param(
    [double]$IntervalSeconds = 2,
    [int]$RecentEvents = 12,
    [string]$LocalSessionSummary = "",
    [switch]$Once,
    [switch]$NoClear,
    [switch]$NoLocalSession
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ArgsList = @(
    "scripts/autodev.py",
    "watch",
    "--interval", $IntervalSeconds,
    "--events", $RecentEvents
)
if ($NoClear) {
    $ArgsList += "--no-clear"
}
if ($NoLocalSession) {
    $ArgsList += "--no-local-session"
}
if ($LocalSessionSummary) {
    $ArgsList += @("--local-session-summary", $LocalSessionSummary)
}
if ($Once) {
    $ArgsList += "--once"
}

& python @ArgsList
exit $LASTEXITCODE
