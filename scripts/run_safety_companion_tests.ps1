$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    python scripts\verify_safety_companion_m0.py
}
finally {
    Pop-Location
}
