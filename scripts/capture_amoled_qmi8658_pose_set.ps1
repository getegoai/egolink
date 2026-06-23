param(
    [string]$Port = "COM9",
    [int]$BaudRate = 115200,
    [string[]]$PoseLabels = @("z_negative", "x_positive", "y_positive"),
    [switch]$CaptureMotion,
    [string]$MotionLabel = "motion",
    [int]$TimeoutSeconds = 25,
    [int]$ReadTimeoutMs = 500,
    [int]$SettleSeconds = 2,
    [string]$SessionId = ("timu004b-qmi8658-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$OutputDir = "",
    [string]$MarkdownReport = "",
    [switch]$NoPrompt,
    [switch]$Analyze,
    [switch]$RunM1Loop,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot "pc_simulator\runtime"

if (-not $OutputDir) {
    $OutputDir = Join-Path $RuntimeDir "timu004b"
}
if (-not $MarkdownReport) {
    $MarkdownReport = Join-Path $OutputDir "$SessionId.pose_quality.md"
}

function Show-Help {
    @"
Capture bounded QMI8658 JSONL windows from ESP32-S3-Touch-AMOLED-2.06.

Examples:
  powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -Analyze -RunM1Loop
  powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels z_negative,x_positive,y_positive -CaptureMotion -Analyze
  powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -PoseLabels z_negative -NoPrompt -Analyze
  powershell -ExecutionPolicy Bypass -File scripts\capture_amoled_qmi8658_pose_set.ps1 -Analyze -MarkdownReport docs\hardware\TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md

The script captures finite windows only. It resets the bridge before each
window, waits for amoled_bridge_done, writes UTF-8 JSONL without BOM, and can
optionally run pose analysis plus the PC Bridge/M1 recording/replay loop.
"@
}

if ($Help) {
    Show-Help
    return
}

function Assert-PoseLabel {
    param([string]$Label)
    $valid = @("x_positive", "x_negative", "y_positive", "y_negative", "z_positive", "z_negative")
    if ($valid -notcontains $Label) {
        throw "Unsupported pose label '$Label'. Use one of: $($valid -join ', ')"
    }
}

function Write-Utf8NoBomText {
    param(
        [string]$Path,
        [string]$Content
    )
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8NoBomLines {
    param(
        [string]$Path,
        [string[]]$Lines
    )
    [System.IO.File]::WriteAllLines($Path, $Lines, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-PythonChecked {
    param(
        [string[]]$Arguments,
        [string]$LogPath
    )
    & python @Arguments *> $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE. See $LogPath"
    }
}

function Invoke-BridgeReset {
    param([System.IO.Ports.SerialPort]$Serial)
    try {
        $Serial.RtsEnable = $true
        Start-Sleep -Milliseconds 120
        $Serial.RtsEnable = $false
        Start-Sleep -Milliseconds 120
    } catch {
        Write-Warning "RTS reset pulse failed: $($_.Exception.Message)"
    }
}

function Read-AmoledBridgeWindow {
    param(
        [string]$Label,
        [string]$Kind,
        [string]$Path
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lines = [System.Collections.Generic.List[string]]::new()
    $skippedNonJson = 0
    $serial = [System.IO.Ports.SerialPort]::new(
        $Port,
        $BaudRate,
        [System.IO.Ports.Parity]::None,
        8,
        [System.IO.Ports.StopBits]::One
    )
    $serial.ReadTimeout = $ReadTimeoutMs
    $serial.NewLine = "`n"
    $serial.Encoding = [System.Text.Encoding]::ASCII

    try {
        $serial.Open()
        Invoke-BridgeReset -Serial $serial
        try {
            $serial.DiscardInBuffer()
        } catch {
            Write-Warning "DiscardInBuffer failed: $($_.Exception.Message)"
        }

        while ((Get-Date) -lt $deadline) {
            try {
                $line = $serial.ReadLine()
            } catch [System.TimeoutException] {
                continue
            }
            $trimmed = $line.Trim().TrimStart([char]0xFEFF)
            if (-not $trimmed) {
                continue
            }
            if (-not $trimmed.StartsWith("{")) {
                $skippedNonJson += 1
                continue
            }
            try {
                $message = $trimmed | ConvertFrom-Json -ErrorAction Stop
                $lines.Add($trimmed)
                if ($message.type -eq "amoled_bridge_done") {
                    break
                }
            } catch {
                $skippedNonJson += 1
                continue
            }
        }
    } finally {
        if ($serial.IsOpen) {
            $serial.Close()
        }
        $serial.Dispose()
    }

    if ($lines.Count -eq 0) {
        throw "No JSONL lines captured for '$Label' on $Port before timeout."
    }

    Write-Utf8NoBomLines -Path $Path -Lines $lines.ToArray()

    $sampleCount = 0
    $whoamiSeen = $false
    $doneSeen = $false
    foreach ($line in $lines) {
        try {
            $message = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        if ($message.type -eq "imu_sample") {
            $sampleCount += 1
        } elseif ($message.type -eq "imu_whoami") {
            $whoamiSeen = $true
        } elseif ($message.type -eq "amoled_bridge_done") {
            $doneSeen = $true
        }
    }

    [pscustomobject]@{
        label = $Label
        kind = $Kind
        path = $Path
        line_count = $lines.Count
        imu_samples = $sampleCount
        whoami_seen = $whoamiSeen
        done_seen = $doneSeen
        skipped_non_json_lines = $skippedNonJson
    }
}

function Invoke-PoseAnalysis {
    param([object[]]$Captures)
    $analysisJson = Join-Path $OutputDir "$SessionId.pose_quality.json"
    $analysisLog = Join-Path $OutputDir "$SessionId.pose_quality.stdout.json"
    $args = @(
        "scripts\analyze_imu_pose_quality.py",
        "--json",
        "--markdown", $MarkdownReport,
        "--title", "# TIMU-004B QMI8658 Manual Pose/Motion Capture Report"
    )
    foreach ($capture in ($Captures | Where-Object { $_.kind -eq "pose" })) {
        $args += @("--pose", "$($capture.label)=$($capture.path)")
    }
    $motionCapture = $Captures | Where-Object { $_.kind -eq "motion" } | Select-Object -First 1
    if ($motionCapture) {
        $args += @("--motion", $motionCapture.path)
    }
    Invoke-PythonChecked -Arguments $args -LogPath $analysisLog
    Copy-Item -LiteralPath $analysisLog -Destination $analysisJson -Force
    return [pscustomobject]@{
        markdown_report = $MarkdownReport
        json_report = $analysisJson
        stdout_log = $analysisLog
    }
}

function Invoke-M1Loop {
    param([object[]]$Captures)
    $eventLog = Join-Path $OutputDir "$SessionId.events.jsonl"
    $bridgeLog = Join-Path $OutputDir "$SessionId.board_bridge.json"
    $recordingDir = Join-Path $RuntimeDir "recordings\$SessionId"
    $recorderLog = Join-Path $OutputDir "$SessionId.session_recorder.json"
    $qualityLog = Join-Path $OutputDir "$SessionId.session_quality.json"
    $replayLog = Join-Path $OutputDir "$SessionId.session_replay.json"

    if (Test-Path -LiteralPath $eventLog) {
        throw "Event log already exists: $eventLog"
    }

    $bridgeArgs = @("scripts\board_bridge.py", "--event-log", $eventLog, "--json")
    foreach ($capture in $Captures) {
        $bridgeArgs += @("--source", "$($capture.label)=$($capture.path)")
    }
    Invoke-PythonChecked -Arguments $bridgeArgs -LogPath $bridgeLog

    $recorderArgs = @(
        "scripts\session_recorder.py",
        "--event-log", $eventLog,
        "--session-id", $SessionId,
        "--output-dir", $recordingDir,
        "--limit", "500",
        "--json"
    )
    Invoke-PythonChecked -Arguments $recorderArgs -LogPath $recorderLog

    $qualityArgs = @("scripts\inspect_session_recording.py", $recordingDir, "--json")
    Invoke-PythonChecked -Arguments $qualityArgs -LogPath $qualityLog

    $replayArgs = @("scripts\replay_session_recording.py", $recordingDir, "--json")
    Invoke-PythonChecked -Arguments $replayArgs -LogPath $replayLog

    return [pscustomobject]@{
        event_log = $eventLog
        recording_dir = $recordingDir
        board_bridge_log = $bridgeLog
        recorder_log = $recorderLog
        quality_log = $qualityLog
        replay_log = $replayLog
    }
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

foreach ($label in $PoseLabels) {
    Assert-PoseLabel -Label $label
}

$captures = @()
foreach ($label in $PoseLabels) {
    if (-not $NoPrompt) {
        Write-Host ""
        Write-Host "Place the AMOLED board in pose '$label' and keep it still."
        Read-Host "Press Enter to capture"
    }
    if ($SettleSeconds -gt 0) {
        Start-Sleep -Seconds $SettleSeconds
    }
    $path = Join-Path $OutputDir "$SessionId-$label.jsonl"
    Write-Host "Capturing $label -> $path"
    $captures += Read-AmoledBridgeWindow -Label $label -Kind "pose" -Path $path
}

if ($CaptureMotion) {
    if (-not $NoPrompt) {
        Write-Host ""
        Write-Host "Move, rotate, or lightly tap the AMOLED board during the motion window."
        Read-Host "Press Enter to capture"
    }
    $path = Join-Path $OutputDir "$SessionId-$MotionLabel.jsonl"
    Write-Host "Capturing $MotionLabel -> $path"
    $captures += Read-AmoledBridgeWindow -Label $MotionLabel -Kind "motion" -Path $path
}

$analysis = $null
if ($Analyze) {
    $analysis = Invoke-PoseAnalysis -Captures $captures
}

$m1 = $null
if ($RunM1Loop) {
    $m1 = Invoke-M1Loop -Captures $captures
}

$summary = [pscustomobject]@{
    ok = $true
    session_id = $SessionId
    port = $Port
    baud_rate = $BaudRate
    output_dir = $OutputDir
    captures = $captures
    analysis = $analysis
    m1_loop = $m1
    source_boundary = "bridge_uplink/unverified"
    formal_imu_acceptance = $false
}
$summaryJson = $summary | ConvertTo-Json -Depth 8
$summaryPath = Join-Path $OutputDir "$SessionId.summary.json"
Write-Utf8NoBomText -Path $summaryPath -Content $summaryJson
Write-Host $summaryJson
