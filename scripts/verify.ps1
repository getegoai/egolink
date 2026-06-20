$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    python -m unittest discover -s quality_tests -v
} finally {
    Pop-Location
}
