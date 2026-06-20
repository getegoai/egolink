param(
    [double]$IntervalSeconds = 2,
    [int]$RecentEvents = 12,
    [switch]$Once,
    [switch]$NoClear
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
if ($Once) {
    $ArgsList += "--once"
}

& python @ArgsList
exit $LASTEXITCODE
