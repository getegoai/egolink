# Bounded read-only IMU window export from the VPS Message Hub database.
#
# This orchestrator:
#   1. scp's the repository's existing read-only exporter to the VPS;
#   2. runs it against the VPS Message Hub DB in read-only mode for ONE named
#      device/test-run; it never writes the DB, restarts the service, or sends
#      device commands;
#   3. scp's imu_windows.jsonl + manifest back into a local reports directory.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\export_vps_imu_windows.ps1 `
#     -TestRunId FT001-FW-20260817-001 -OutputDir reports\field_validation\FT-001-20260817-001\imu_export
param(
    [string]$HostName = "203.0.113.10",
    [string]$User = "root",
    [string]$SshKey = (Join-Path $env:USERPROFILE ".ssh\egolink_vps_ed25519"),
    [string]$DeviceId = "ego-link-r1-connectivity-001",
    [Parameter(Mandatory = $true)][string]$TestRunId,
    [int]$MaxFrames = 1000,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"

$SshOpts = @("-i", $SshKey, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")
$RemoteTarget = "${User}@${HostName}"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$exporter = Join-Path $repoRoot "scripts\export_imu_windows.py"
$runner = Join-Path $repoRoot "tools\vps_export_imu_runner.sh"
if (-not (Test-Path $exporter)) { throw "exporter not found: $exporter" }
if (-not (Test-Path $runner)) { throw "runner not found: $runner" }

Write-Host "=== 1/3 transfer read-only export tooling ==="
& scp @SshOpts $exporter "${RemoteTarget}:/tmp/bounded_export_imu_windows.py"
if ($LASTEXITCODE -ne 0) { throw "scp exporter failed with exit code $LASTEXITCODE" }
& scp @SshOpts $runner "${RemoteTarget}:/tmp/vps_export_imu_runner.sh"
if ($LASTEXITCODE -ne 0) { throw "scp runner failed with exit code $LASTEXITCODE" }

Write-Host "=== 2/3 run bounded read-only export on VPS ==="
& ssh @SshOpts $RemoteTarget "bash /tmp/vps_export_imu_runner.sh '$DeviceId' '$TestRunId' '$MaxFrames'"
if ($LASTEXITCODE -ne 0) { throw "remote export failed with exit code $LASTEXITCODE" }

Write-Host "=== 3/3 fetch results ==="
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
& scp @SshOpts "${RemoteTarget}:/tmp/egolink-imu-export/${TestRunId}/imu_windows.jsonl" (Join-Path $OutputDir "imu_windows.jsonl")
if ($LASTEXITCODE -ne 0) { throw "scp imu_windows.jsonl failed with exit code $LASTEXITCODE" }
& scp @SshOpts "${RemoteTarget}:/tmp/egolink-imu-export/${TestRunId}/imu_window_export_manifest.json" (Join-Path $OutputDir "imu_window_export_manifest.json")
if ($LASTEXITCODE -ne 0) { throw "scp manifest failed with exit code $LASTEXITCODE" }

Write-Host "EXPORT_COMPLETE output_dir=$OutputDir"