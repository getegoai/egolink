param(
    [string]$Port = "",
    [int]$BaudRate = 115200,
    [string]$HubUrl = "http://127.0.0.1:8790",
    [string]$TokenFile = "",
    [string]$DeviceId = "",
    [int]$SampleCount = 1,
    [double]$PollIntervalSec = 30,
    [int]$ReadWindowSeconds = 8,
    [int]$ReadTimeoutMs = 500,
    [int]$HttpTimeoutSec = 10,
    [string]$SessionId = ("amoled-d1-status-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$OutputDir = "",
    [switch]$Reset,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $TokenFile) {
    $TokenFile = Join-Path $RepoRoot "server\runtime\vps_message_hub_token.txt"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "pc_simulator\runtime\amoled_d1_status_sidecar"
}

function Show-Help {
    @"
Mirror the D1 Web/API status onto the AMOLED screen sidecar.

Examples:
  powershell -ExecutionPolicy Bypass -File scripts\run_amoled_d1_status_sidecar.ps1 -HubUrl http://203.0.113.10:8790
  powershell -ExecutionPolicy Bypass -File scripts\run_amoled_d1_status_sidecar.ps1 -Port COM9 -SampleCount 12 -PollIntervalSec 30

The script is finite. It reads /api/state, sends status_update JSON to the
AMOLED USB Serial/JTAG port, records board JSONL, and exits. It does not send
commands to the 4G board or the Message Hub command queue.
"@
}

if ($Help) {
    Show-Help
    return
}

if ($SampleCount -lt 1) {
    throw "SampleCount must be >= 1."
}
if ($PollIntervalSec -lt 0) {
    throw "PollIntervalSec must be >= 0."
}
if ($ReadWindowSeconds -lt 1) {
    throw "ReadWindowSeconds must be >= 1."
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

function Get-Field {
    param(
        [object]$Object,
        [string]$Name
    )
    if ($null -eq $Object) {
        return $null
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($prop) {
        return $prop.Value
    }
    return $null
}

function First-Text {
    param(
        [object[]]$Values,
        [string]$Default = "unknown"
    )
    foreach ($value in $Values) {
        if ($null -ne $value -and "$value" -ne "") {
            return "$value"
        }
    }
    return $Default
}

function Limit-Text {
    param(
        [string]$Text,
        [int]$Max = 72
    )
    if ($null -eq $Text) {
        return ""
    }
    if ($Text.Length -le $Max) {
        return $Text
    }
    return $Text.Substring(0, $Max)
}

function Format-Number {
    param(
        [object]$Value,
        [string]$Format = "0"
    )
    if ($null -eq $Value -or "$Value" -eq "") {
        return $null
    }
    try {
        return ([double]$Value).ToString($Format, [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        return $null
    }
}

function Format-Freshness {
    param([object]$Value)
    $text = Format-Number -Value $Value -Format "0"
    if ($text) {
        return "${text}s"
    }
    return "unknown"
}

function Read-MessageHubToken {
    $envToken = [Environment]::GetEnvironmentVariable("EGOLINK_MESSAGE_HUB_TOKEN")
    if ($envToken) {
        return $envToken
    }
    if ($TokenFile -and (Test-Path -LiteralPath $TokenFile)) {
        return (Get-Content -LiteralPath $TokenFile -Raw).Trim()
    }
    return ""
}

function Invoke-HubState {
    param([string]$Token)
    $headers = @{}
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    $uri = $HubUrl.TrimEnd("/") + "/api/state"
    return Invoke-RestMethod -Method Get -Uri $uri -Headers $headers -TimeoutSec $HttpTimeoutSec
}

function Select-D1Device {
    param(
        [object]$State,
        [string]$PreferredDeviceId
    )
    $devicesValue = Get-Field $State "devices"
    if ($null -eq $devicesValue) {
        return $null
    }
    foreach ($device in @($devicesValue)) {
        if ($null -eq $device) {
            continue
        }
        if ($PreferredDeviceId -and (Get-Field $device "device_id") -ne $PreferredDeviceId) {
            continue
        }
        if (Get-Field $device "d1_link") {
            return $device
        }
    }
    return $null
}

function New-D1StatusPayload {
    param(
        [object]$State,
        [string]$PreferredDeviceId
    )
    $device = Select-D1Device -State $State -PreferredDeviceId $PreferredDeviceId
    if ($null -eq $device) {
        return [ordered]@{
            summary = "D1 waiting / no device"
            lte = "unknown"
            location = "Loc waiting"
            battery = "Battery unknown"
            footer = "No d1_link in /api/state"
        }
    }

    $d1 = Get-Field $device "d1_link"
    $status = First-Text @((Get-Field $d1 "status")) "waiting"
    $surface = Get-Field $d1 "map_surface"
    $freshness = Get-Field $d1 "upload_freshness"
    $uplink = Get-Field $d1 "uplink_metrics"
    $powerCurve = Get-Field $d1 "power_curve"
    $components = Get-Field (Get-Field $d1 "evidence") "components"
    $cell = Get-Field $components "cell_lte"
    $gnss = Get-Field $components "gnss"
    $power = Get-Field $components "power"

    $freshText = Format-Freshness (Get-Field $freshness "freshness_s")
    $rat = First-Text @((Get-Field $cell "rat")) "LTE"
    $registration = First-Text @((Get-Field $cell "registration_state")) "unknown"
    $pdp = First-Text @((Get-Field $cell "pdp_state")) "unknown"
    $lteText = Limit-Text "$rat $registration/$pdp"
    $summary = Limit-Text "D1 $status fresh $freshText / $lteText"

    $lat = Get-Field $surface "lat"
    $lon = Get-Field $surface "lon"
    $latText = Format-Number -Value $lat -Format "0.00000"
    $lonText = Format-Number -Value $lon -Format "0.00000"
    if ($latText -and $lonText) {
        $location = "Coord $latText,$lonText"
    } else {
        $mapMode = First-Text @((Get-Field $surface "mode")) "waiting"
        $gnssState = First-Text @((Get-Field $gnss "state"), (Get-Field $gnss "reason_code")) "gnss_unknown"
        $location = Limit-Text "Loc $mapMode / $gnssState"
    }

    $socText = Format-Number -Value (Get-Field $power "soc_pct") -Format "0"
    if (-not $socText) {
        $socText = Format-Number -Value (Get-Field (Get-Field $powerCurve "latest") "soc_pct") -Format "0"
    }
    $mvText = Format-Number -Value (Get-Field $power "battery_mv") -Format "0"
    if (-not $mvText) {
        $mvText = Format-Number -Value (Get-Field (Get-Field $powerCurve "latest") "battery_mv") -Format "0"
    }
    if ($socText -or $mvText) {
        $battery = Limit-Text "Battery $(First-Text @($socText) "?")% / $(First-Text @($mvText) "?")mV"
    } else {
        $battery = "Battery unknown"
    }

    $ok = First-Text @((Get-Field $uplink "raw_post_success_count")) "?"
    $fail = First-Text @((Get-Field $uplink "raw_post_failure_count")) "?"
    $locCount = First-Text @((Get-Field $uplink "location_event_count")) "?"
    $footer = Limit-Text "POST $ok ok / $fail fail / loc $locCount"

    return [ordered]@{
        summary = $summary
        lte = $lteText
        location = $location
        battery = $battery
        footer = $footer
        map_mode = First-Text @((Get-Field $surface "mode")) "unknown"
    }
}

function New-D1StatusUpdateCommandJson {
    param(
        [object]$State,
        [string]$CommandId,
        [string]$Session,
        [string]$PreferredDeviceId
    )
    $device = Select-D1Device -State $State -PreferredDeviceId $PreferredDeviceId
    $payload = New-D1StatusPayload -State $State -PreferredDeviceId $PreferredDeviceId
    $sourceDeviceId = if ($device) { Get-Field $device "device_id" } else { $PreferredDeviceId }
    $message = [ordered]@{
        protocol_version = "0.2"
        source = "pc-bridge-d1-status-sidecar"
        type = "status_update"
        cmd_id = $CommandId
        source_device_id = $sourceDeviceId
        payload = $payload
    }
    return ($message | ConvertTo-Json -Compress -Depth 8)
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

if (-not $Port) {
    $Port = Find-AmoledPort
}
if (-not $Port) {
    throw "Could not find ESP32-S3-Touch-AMOLED-2.06 USB Serial/JTAG port. Pass -Port explicitly."
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$jsonlPath = Join-Path $OutputDir "$SessionId.jsonl"
$summaryPath = Join-Path $OutputDir "$SessionId.summary.json"
$captured = [System.Collections.Generic.List[string]]::new()
$skippedNonJson = 0
$statusRendered = 0
$commandAck = 0
$fetchErrors = 0
$commandsSent = 0
$lastPayload = $null
$token = Read-MessageHubToken

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

    for ($index = 0; $index -lt $SampleCount; $index++) {
        $cmdId = "$SessionId-status-$($index + 1)"
        try {
            $state = Invoke-HubState -Token $token
            $commandJson = New-D1StatusUpdateCommandJson -State $state -CommandId $cmdId -Session $SessionId -PreferredDeviceId $DeviceId
            $lastPayload = (($commandJson | ConvertFrom-Json).payload)
            $serial.WriteLine($commandJson)
            $commandsSent += 1
            Write-Host "SENT status_update $cmdId"
        } catch {
            $fetchErrors += 1
            Write-Warning "D1 state fetch/send failed for ${cmdId}: $($_.Exception.Message)"
            continue
        }

        $deadline = (Get-Date).AddSeconds($ReadWindowSeconds)
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
            } catch {
                $skippedNonJson += 1
                continue
            }

            $captured.Add($trimmed)
            Write-Output $trimmed

            if ($message.type -eq "command_ack" -and $message.cmd_id -eq $cmdId) {
                $commandAck += 1
            }
            if ($message.type -eq "status_rendered" -and $message.cmd_id -eq $cmdId) {
                $statusRendered += 1
                break
            }
        }

        if ($index -lt ($SampleCount - 1) -and $PollIntervalSec -gt 0) {
            Start-Sleep -Seconds $PollIntervalSec
        }
    }
} finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}

Write-Utf8NoBomLines -Path $jsonlPath -Lines $captured.ToArray()

$ok = ($fetchErrors -eq 0) -and ($commandsSent -eq $SampleCount) -and ($statusRendered -eq $SampleCount)
$summary = [ordered]@{
    ok = $ok
    session_id = $SessionId
    hub_url = $HubUrl.TrimEnd("/")
    device_id = $DeviceId
    port = $Port
    baud_rate = $BaudRate
    sample_count = $SampleCount
    commands_sent = $commandsSent
    command_ack_count = $commandAck
    status_rendered_count = $statusRendered
    fetch_error_count = $fetchErrors
    skipped_non_json_lines = $skippedNonJson
    jsonl_path = $jsonlPath
    last_status_payload = $lastPayload
    scope = [ordered]@{
        reads_message_hub_state = $true
        writes_amoled_serial = $true
        sends_message_hub_commands = $false
        contacts_4g_board_serial = $false
        changes_firmware = $false
        claims_location_accuracy = $false
        claims_battery_life = $false
    }
}
$summaryJson = $summary | ConvertTo-Json -Depth 8
Write-Utf8NoBomText -Path $summaryPath -Content $summaryJson
Write-Host $summaryJson

if (-not $ok) {
    exit 2
}
