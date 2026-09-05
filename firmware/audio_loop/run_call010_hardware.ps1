[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Port,

    [Parameter(Mandatory = $true)]
    [string]$EvidenceDir,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^CALL-010-[0-9]{8}-[0-9]{3}$')]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedAppSha256,

    [Parameter(Mandatory = $true)]
    [switch]$OperatorAuthorized,

    [ValidateRange(195, 240)]
    [int]$CaptureTimeoutSeconds = 215,

    [string]$BuildDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $OperatorAuthorized) {
    throw 'CALL-010 hardware execution requires -OperatorAuthorized.'
}
if ([string]::IsNullOrWhiteSpace($BuildDir)) {
    $BuildDir = Join-Path $PSScriptRoot 'build_operator_static'
}
$idfProfile = 'C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1'
if (-not (Test-Path -LiteralPath $idfProfile)) {
    throw "Missing pinned ESP-IDF 5.4.2 profile: $idfProfile"
}
. $idfProfile | Out-Null
$idfPython = Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $idfPython)) {
    throw 'Pinned ESP-IDF Python was not resolved after environment activation.'
}
if ($Port -notmatch '^COM\d+$') {
    throw "Invalid serial port: $Port"
}

$portDevice = Get-PnpDevice -PresentOnly -Class Ports |
    Where-Object { $_.FriendlyName -match "\($([regex]::Escape($Port))\)$" }
if (@($portDevice).Count -ne 1) {
    throw "Expected exactly one present PnP port for $Port."
}
$portDevice = @($portDevice)[0]
if ($portDevice.InstanceId -notmatch '^USB\\VID_303A&PID_1001&MI_00\\') {
    throw "Refusing non-wearable USB identity on ${Port}: $($portDevice.InstanceId)"
}
if ($portDevice.InstanceId -match 'VID_1A86|VID_05C6|VID_1E0E') {
    throw "Refusing connectivity-node/modem identity on ${Port}."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$resolvedEvidenceDir = [System.IO.Path]::GetFullPath(
    (Join-Path $repoRoot $EvidenceDir)
)
$allowedEvidenceRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $repoRoot 'reports\board_validation')
)
if (-not $resolvedEvidenceDir.StartsWith(
        $allowedEvidenceRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "EvidenceDir must be below $allowedEvidenceRoot"
}
if ((Split-Path -Leaf $resolvedEvidenceDir) -ne $RunId) {
    throw "EvidenceDir leaf must exactly match RunId $RunId"
}
if (Test-Path -LiteralPath $resolvedEvidenceDir) {
    $existing = Get-ChildItem -LiteralPath $resolvedEvidenceDir -Force
    if (@($existing).Count -ne 0) {
        throw "Refusing to overwrite non-empty evidence directory: $resolvedEvidenceDir"
    }
} else {
    New-Item -ItemType Directory -Path $resolvedEvidenceDir | Out-Null
}

$resolvedBuildDir = (Resolve-Path -LiteralPath $BuildDir).Path
$appImage = Join-Path $resolvedBuildDir 'egolink_call010_audio_loop.bin'
if (-not (Test-Path -LiteralPath $appImage)) {
    throw "Missing operator image: $appImage"
}
$actualAppSha256 = (Get-FileHash -LiteralPath $appImage -Algorithm SHA256).Hash
if ($actualAppSha256 -ne $ExpectedAppSha256.ToUpperInvariant()) {
    throw "Operator image SHA-256 mismatch: expected $ExpectedAppSha256, got $actualAppSha256"
}

$startedAt = [DateTimeOffset]::Now
$gitCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$usbComposite = Get-PnpDevice -PresentOnly -Class USB |
    Where-Object { $_.InstanceId -match '^USB\\VID_303A&PID_1001\\' } |
    Select-Object -First 1
$manifest = [ordered]@{
    task_id = 'CALL-010'
    run_id = $RunId
    operator_authorized = $true
    authorization_scope = 'wearable only; low-volume bounded audio; no raw audio retention; do not touch 4G board'
    started_at = $startedAt.ToString('o')
    board_id = 'wearable-node-001'
    board_family = 'ESP32-S3-Touch-AMOLED-2.06'
    physical_pcb_revision = 'unknown_pending_operator_visual_inspection'
    serial_port = $Port
    port_pnp_instance_id = $portDevice.InstanceId
    usb_composite_instance_id = if ($null -eq $usbComposite) { $null } else { $usbComposite.InstanceId }
    connection_path = 'USB Serial/JTAG data cable; USB-attached engineering run'
    repository_commit = $gitCommit
    esp_idf_path = $env:IDF_PATH
    esp_idf_python = $idfPython
    build_dir = $resolvedBuildDir
    app_image = $appImage
    app_sha256 = $actualAppSha256
    no_audio_storage = $true
    configured_phases_seconds = [ordered]@{
        output_chirp = 30
        input_metrics = 30
        attenuated_local_loop = 120
    }
    configured_safe_volume = 12
    controlled_start = 'esptool --after no_reset; open serial; RTS reset pulse'
    capture_timeout_seconds = $CaptureTimeoutSeconds
}
$manifestPath = Join-Path $resolvedEvidenceDir 'run_manifest.json'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogPath,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )
    & $Command 2>&1 | Tee-Object -FilePath $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE; see $LogPath"
    }
}

$chipLog = Join-Path $resolvedEvidenceDir 'chip_identity.log'
Invoke-LoggedCommand -LogPath $chipLog -Command {
    & $idfPython -m esptool --port $Port chip_id
}
$chipText = Get-Content -LiteralPath $chipLog -Raw
if ($chipText -notmatch 'ESP32-S3') {
    throw "Read-only chip identity did not report ESP32-S3; see $chipLog"
}
if ($chipText -notmatch '02:00:00:00:00:01') {
    throw "Chip MAC does not match wearable-node-001; see $chipLog"
}

$flashLog = Join-Path $resolvedEvidenceDir 'flash.log'
Invoke-LoggedCommand -LogPath $flashLog -Command {
    Push-Location $resolvedBuildDir
    try {
        & $idfPython -m esptool --chip esp32s3 -p $Port -b 460800 `
            --before default_reset --after no_reset write_flash `
            --flash_mode dio --flash_freq 80m --flash_size 16MB `
            0x0 bootloader/bootloader.bin `
            0x10000 egolink_call010_audio_loop.bin `
            0x8000 partition_table/partition-table.bin
    } finally {
        Pop-Location
    }
}

$serialLog = Join-Path $resolvedEvidenceDir 'serial.log'
$serial = [System.IO.Ports.SerialPort]::new(
    $Port,
    115200,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$serial.ReadTimeout = 250
$serial.WriteTimeout = 250
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$openDeadline = [DateTimeOffset]::Now.AddSeconds(20)
while (-not $serial.IsOpen -and [DateTimeOffset]::Now -lt $openDeadline) {
    try {
        $serial.Open()
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if (-not $serial.IsOpen) {
    throw "Unable to open $Port for bounded serial evidence."
}

$sequenceComplete = $false
$captureStartedAt = [DateTimeOffset]::Now
$captureDeadline = $captureStartedAt.AddSeconds($CaptureTimeoutSeconds)
$writer = [System.IO.StreamWriter]::new($serialLog, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $serial.DiscardInBuffer()
    $serial.DtrEnable = $false
    $serial.RtsEnable = $true
    Start-Sleep -Milliseconds 200
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    Start-Sleep -Milliseconds 200
    $serial.DtrEnable = $false
    while ([DateTimeOffset]::Now -lt $captureDeadline) {
        try {
            $line = $serial.ReadLine().TrimEnd("`r")
            $record = '{0} {1}' -f [DateTimeOffset]::Now.ToString('o'), $line
            $writer.WriteLine($record)
            $writer.Flush()
            Write-Host $record
            if ($line -match 'AUDIO_SEQUENCE_COMPLETE') {
                $sequenceComplete = $true
                break
            }
        } catch [System.TimeoutException] {
            continue
        }
    }
} finally {
    $writer.Dispose()
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}

$serialText = if (Test-Path -LiteralPath $serialLog) {
    Get-Content -LiteralPath $serialLog -Raw
} else {
    ''
}
$requiredPatterns = [ordered]@{
    output_start = 'AUDIO_PHASE_START phase=output_chirp seconds=30'
    output_end = 'AUDIO_PHASE_END phase=output_chirp result=ESP_OK'
    input_start = 'AUDIO_PHASE_START phase=input_metrics seconds=30'
    input_end = 'AUDIO_PHASE_END phase=input_metrics result=ESP_OK'
    duplex_start = 'AUDIO_PHASE_START phase=attenuated_local_loop seconds=120'
    duplex_end = 'AUDIO_PHASE_END phase=attenuated_local_loop result=ESP_OK'
    final_safe = 'AUDIO_SEQUENCE_COMPLETE result=ESP_OK speaker_pa_off_verified=true deadline_expired=false'
}
$checks = [ordered]@{}
foreach ($entry in $requiredPatterns.GetEnumerator()) {
    $checks[$entry.Key] = $serialText.Contains($entry.Value)
}
$fatalPattern = 'Guru Meditation|Brownout|watchdog|abort\(\)|assert failed|LoadProhibited|StoreProhibited'
$fatalMarkers = [regex]::Matches($serialText, $fatalPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase) |
    ForEach-Object { $_.Value } |
    Select-Object -Unique
$allChecksPassed = -not ($checks.Values -contains $false)
$passed = $sequenceComplete -and $allChecksPassed -and @($fatalMarkers).Count -eq 0
$finishedAt = [DateTimeOffset]::Now
$summary = [ordered]@{
    task_id = 'CALL-010'
    run_id = $RunId
    result = if ($passed) { 'PASS_LOGICAL_RUNTIME' } else { 'FAIL_OR_INCOMPLETE' }
    started_at = $startedAt.ToString('o')
    capture_started_at = $captureStartedAt.ToString('o')
    finished_at = $finishedAt.ToString('o')
    board_id = 'wearable-node-001'
    serial_port = $Port
    app_sha256 = $actualAppSha256
    no_audio_storage = $true
    controlled_start = 'esptool --after no_reset; serial opened before RTS reset pulse'
    sequence_complete_seen = $sequenceComplete
    checks = $checks
    fatal_markers = @($fatalMarkers)
    audible_output_operator_confirmation = 'pending'
    physical_pcb_revision = 'unknown_pending_operator_visual_inspection'
    non_claims = @(
        'No acoustic SPL/AEC/AGC/echo/product-power claim.',
        'No LTE/RTC or P0-CALL PASS claim.',
        'Serial aggregate metrics do not prove physical audibility without operator confirmation.',
        'Current capture-then-play loop is not application-level concurrent DMA queue evidence.'
    )
    evidence = [ordered]@{
        manifest = $manifestPath
        chip_identity = $chipLog
        flash = $flashLog
        serial = $serialLog
    }
}
$summaryPath = Join-Path $resolvedEvidenceDir 'result.json'
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8

$report = @"
# CALL-010 Hardware Run

- Run: $RunId
- Result: $($summary.result)
- Board: wearable-node-001 / ESP32-S3-Touch-AMOLED-2.06
- Physical PCB revision: unknown_pending_operator_visual_inspection
- Connection: $Port, $($portDevice.InstanceId)
- App SHA-256: $actualAppSha256
- Raw audio retained: false
- Controlled start: esptool after=no_reset; serial opened before RTS reset pulse
- Sequence complete marker: $sequenceComplete
- Fatal markers: $(@($fatalMarkers) -join ', ')
- Audible output operator confirmation: pending

The result is bounded engineering evidence only. It does not establish SPL,
AEC/AGC, echo, product power, LTE/RTC media, application-level concurrent DMA,
or P0-CALL PASS.
"@
$report | Set-Content -LiteralPath (Join-Path $resolvedEvidenceDir 'report.md') -Encoding utf8

if (-not $passed) {
    throw "CALL-010 hardware run did not satisfy its serial/runtime checks; see $summaryPath"
}

Write-Host "CALL-010 bounded hardware run passed serial/runtime checks. Evidence: $resolvedEvidenceDir"
