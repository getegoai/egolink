param(
    [string]$Port = "",
    [int]$BaudRate = 115200,
    [int]$WaitSeconds = 30,
    [int]$ReadTimeoutMs = 500,
    [string]$SessionId = ("demo-v0-2-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$OutputDir = "",
    [switch]$Reset,
    [switch]$RequireConfirmation,
    [switch]$WaitForMotionEvent,
    [switch]$SendStatusUpdate,
    [string]$StatusLte = "online",
    [string]$StatusLocation = "estimate_without_coordinate",
    [string]$StatusBattery = "unknown",
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "pc_simulator\runtime\demo_v0_2"
}

function Show-Help {
    @"
Send the Demo v0.2 PC Bridge ask_user command to ESP32-S3-Touch-AMOLED-2.06.

Examples:
  powershell -ExecutionPolicy Bypass -File scripts\run_amoled_ask_user_demo.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run_amoled_ask_user_demo.ps1 -SendStatusUpdate
  powershell -ExecutionPolicy Bypass -File scripts\run_amoled_ask_user_demo.ps1 -Reset -RequireConfirmation
  powershell -ExecutionPolicy Bypass -File scripts\run_amoled_ask_user_demo.ps1 -Port COM9 -WaitSeconds 45

The script is finite. It opens the AMOLED USB Serial/JTAG port, sends one
optional status_update JSON command, sends one versioned ask_user JSON
command, records board JSONL, and exits.
"@
}

if ($Help) {
    Show-Help
    return
}

function Find-AmoledPort {
    $serial = Get-CimInstance Win32_SerialPort |
        Where-Object { $_.PNPDeviceID -match "VID_303A&PID_1001" } |
        Select-Object -First 1
    if ($serial) {
        return $serial.DeviceID
    }

    $pnp = Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.PNPDeviceID -match "VID_303A&PID_1001" -and $_.Name -match "\(COM\d+\)" } |
        Select-Object -First 1
    if ($pnp -and $pnp.Name -match "(COM\d+)") {
        return $Matches[1]
    }

    return ""
}

function Write-Utf8NoBomLines {
    param(
        [string]$Path,
        [string[]]$Lines
    )
    [System.IO.File]::WriteAllLines($Path, $Lines, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8NoBomText {
    param(
        [string]$Path,
        [string]$Content
    )
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
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

function New-AskUserCommandJson {
    param(
        [string]$CommandId,
        [string]$Session
    )
    $message = [ordered]@{
        protocol_version = "0.2"
        source = "pc-bridge"
        target = "wearable-node-001"
        type = "ask_user"
        cmd = "ask_user"
        cmd_id = $CommandId
        seq = 1
        timestamp_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        session_id = $Session
        payload = [ordered]@{
            text = "Impact detected. Are you safe?"
            options = @("safe", "help")
        }
    }
    return ($message | ConvertTo-Json -Compress -Depth 6)
}

function New-StatusUpdateCommandJson {
    param(
        [string]$CommandId,
        [string]$Session,
        [string]$Lte,
        [string]$Location,
        [string]$Battery
    )
    $message = [ordered]@{
        protocol_version = "0.2"
        source = "pc-bridge-display"
        target = "wearable-node-001"
        type = "status_update"
        cmd = "status_update"
        cmd_id = $CommandId
        seq = 0
        timestamp_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        session_id = $Session
        payload = [ordered]@{
            summary = "D1 sidecar display"
            lte = $Lte
            location = $Location
            battery = $Battery
            footer = "Waiting for safety prompt"
        }
    }
    return ($message | ConvertTo-Json -Compress -Depth 6)
}

if (-not $Port) {
    $Port = Find-AmoledPort
}
if (-not $Port) {
    throw "Could not find ESP32-S3-Touch-AMOLED-2.06 USB Serial/JTAG port. Pass -Port explicitly."
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$cmdId = "demo-v0-2-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$statusCmdId = "$cmdId-status"
$commandJson = New-AskUserCommandJson -CommandId $cmdId -Session $SessionId
$statusUpdateJson = New-StatusUpdateCommandJson -CommandId $statusCmdId -Session $SessionId -Lte $StatusLte -Location $StatusLocation -Battery $StatusBattery
$jsonlPath = Join-Path $OutputDir "$SessionId.jsonl"
$summaryPath = Join-Path $OutputDir "$SessionId.summary.json"
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$statusSendAfter = (Get-Date).AddMilliseconds(800)
$askSendDelayMs = 800
if ($SendStatusUpdate) {
    $askSendDelayMs = 1600
}
$askSendAfter = (Get-Date).AddMilliseconds($askSendDelayMs)
$sent = $false
$statusSent = $false
$rendered = $false
$statusRendered = $false
$confirmed = $false
$confirmation = ""
$captured = [System.Collections.Generic.List[string]]::new()
$skippedNonJson = 0
$motionSeen = $false

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
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    if ($Reset) {
        Invoke-BridgeReset -Serial $serial
        Start-Sleep -Milliseconds 800
    }
    try {
        $serial.DiscardInBuffer()
    } catch {
        Write-Warning "DiscardInBuffer failed: $($_.Exception.Message)"
    }

    while ((Get-Date) -lt $deadline) {
        if ($SendStatusUpdate -and -not $statusSent -and (Get-Date) -ge $statusSendAfter) {
            $serial.WriteLine($statusUpdateJson)
            Write-Host "SENT $statusUpdateJson"
            $statusSent = $true
        }

        if (-not $sent) {
            $shouldSend = $false
            if ($WaitForMotionEvent) {
                if ($motionSeen) {
                    $shouldSend = $true
                }
            } else {
                if ((Get-Date) -ge $askSendAfter) {
                    $shouldSend = $true
                }
            }
            if ($shouldSend) {
                $serial.WriteLine($commandJson)
                Write-Host "SENT $commandJson"
                $sent = $true
            }
        }

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
        } catch {
            $skippedNonJson += 1
            continue
        }

        $captured.Add($trimmed)
        Write-Output $trimmed

        if ($message.type -eq "hello" -or $message.type -eq "display_ready") {
            if (-not $sent -and -not $WaitForMotionEvent -and -not $SendStatusUpdate) {
                $serial.WriteLine($commandJson)
                Write-Host "SENT $commandJson"
                $sent = $true
            }
        }
        if ($message.type -eq "motion_event" -or $message.event_type -eq "motion_event") {
            $motionSeen = $true
            if (-not $sent -and $WaitForMotionEvent) {
                $serial.WriteLine($commandJson)
                Write-Host "SENT $commandJson"
                $sent = $true
            }
        }
        if ($message.type -eq "status_rendered" -and $message.cmd_id -eq $statusCmdId) {
            $statusRendered = $true
            if (-not $sent -and -not $WaitForMotionEvent) {
                $serial.WriteLine($commandJson)
                Write-Host "SENT $commandJson"
                $sent = $true
            }
        }
        if ($message.type -eq "ask_user_rendered" -and $message.cmd_id -eq $cmdId) {
            $rendered = $true
            if (-not $RequireConfirmation) {
                break
            }
        }
        if ($message.type -eq "user_confirmation" -and $message.cmd_id -eq $cmdId) {
            $confirmed = $true
            $confirmation = [string]$message.response
            break
        }
    }
} finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}

Write-Utf8NoBomLines -Path $jsonlPath -Lines $captured.ToArray()

$ok = $rendered -and ((-not $RequireConfirmation) -or $confirmed) -and ((-not $SendStatusUpdate) -or $statusRendered)
$summary = [ordered]@{
    ok = $ok
    session_id = $SessionId
    port = $Port
    baud_rate = $BaudRate
    status_update_sent = $statusSent
    status_command_id = $statusCmdId
    status_rendered = $statusRendered
    command_sent = $sent
    command_id = $cmdId
    ask_user_rendered = $rendered
    user_confirmation = $confirmed
    response = $confirmation
    jsonl_path = $jsonlPath
    skipped_non_json_lines = $skippedNonJson
    motion_event_seen = $motionSeen
}
$summaryJson = $summary | ConvertTo-Json -Depth 6
Write-Utf8NoBomText -Path $summaryPath -Content $summaryJson
Write-Host $summaryJson

if (-not $ok) {
    exit 2
}
