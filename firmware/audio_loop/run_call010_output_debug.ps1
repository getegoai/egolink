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
    [switch]$OutputDiagnosticAuthorized,

    [ValidateRange(35, 60)]
    [int]$CaptureTimeoutSeconds = 45,

    [string]$BuildDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedMac = '02:00:00:00:00:01'
$expectedCompositeInstanceId = 'USB\VID_303A&PID_1001\44:1B:F6:85:1D:78'
$expectedCountdown = 15
$expectedStages = @(
    [ordered]@{ stage = 1; volume = 55; register = '0x99' },
    [ordered]@{ stage = 2; volume = 70; register = '0xa8' },
    [ordered]@{ stage = 3; volume = 85; register = '0xb7' }
)
$expectedToneSeconds = 2
$expectedGapSeconds = 2
$expectedPcmPeak = 5000
$expectedFrequencyHz = 1000
$expectedFrames = 100
$expectedBytesPerFrame = 1280
$expectedBytesPerStage = 128000

if (-not $OutputDiagnosticAuthorized) {
    throw 'CALL-010 staged output diagnostic requires -OutputDiagnosticAuthorized.'
}
if ([string]::IsNullOrWhiteSpace($BuildDir)) {
    $BuildDir = Join-Path $PSScriptRoot 'build_output_diagnostic_static'
}
if ($Port -notmatch '^COM\d+$') {
    throw "Invalid serial port: $Port"
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

$manifestPath = Join-Path $resolvedEvidenceDir 'run_manifest.json'
$chipLog = Join-Path $resolvedEvidenceDir 'chip_identity.log'
$flashLog = Join-Path $resolvedEvidenceDir 'flash.log'
$serialLog = Join-Path $resolvedEvidenceDir 'serial.log'
$summaryPath = Join-Path $resolvedEvidenceDir 'result.json'
$reportPath = Join-Path $resolvedEvidenceDir 'report.md'
$startedAt = [DateTimeOffset]::Now
$operatorFlashStarted = $false
$captureStartedAt = $null

function Write-Utf8NoBomText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [AllowEmptyString()]
        [Parameter(Mandatory = $true)]
        [string]$Content
    )
    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Write-JsonEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Value
    )
    Write-Utf8NoBomText -Path $Path -Content (
        $Value | ConvertTo-Json -Depth 12
    )
}

function Invoke-CapturedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$LogPath
    )

    $capturedLines = @(
        & $FilePath @ArgumentList 2>&1 |
            ForEach-Object { $_.ToString().Replace("`0", '') }
    )
    $exitCode = $LASTEXITCODE
    $capturedText = $capturedLines -join [Environment]::NewLine
    if ($capturedText.Length -gt 0) {
        $capturedText += [Environment]::NewLine
    }
    Write-Utf8NoBomText -Path $LogPath -Content $capturedText
    foreach ($line in $capturedLines) {
        Write-Host $line
    }
    return [pscustomobject]@{
        exit_code = $exitCode
        text = $capturedText
    }
}

function Test-ContainsLiteral {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [string]$Literal
    )
    return $Text.Contains($Literal)
}

try {
    $portDevices = @(
        Get-PnpDevice -PresentOnly -Class Ports |
            Where-Object {
                $_.FriendlyName -match "\($([regex]::Escape($Port))\)$"
            }
    )
    if ($portDevices.Count -ne 1) {
        throw "Expected exactly one present PnP port for $Port."
    }
    $portDevice = $portDevices[0]
    if ($portDevice.InstanceId -notmatch '^USB\\VID_303A&PID_1001&MI_00\\') {
        throw "Refusing non-wearable USB identity on ${Port}: $($portDevice.InstanceId)"
    }
    if ($portDevice.InstanceId -match 'VID_1A86|VID_05C6|VID_1E0E') {
        throw "Refusing connectivity-node/modem identity on ${Port}."
    }

    $matchingCompositeDevices = @(
        Get-PnpDevice -PresentOnly -Class USB |
            Where-Object { $_.InstanceId -ieq $expectedCompositeInstanceId }
    )
    if ($matchingCompositeDevices.Count -ne 1) {
        throw 'Expected wearable USB composite identity is not uniquely present.'
    }

    $resolvedBuildDir = (Resolve-Path -LiteralPath $BuildDir).Path
    $appImage = Join-Path $resolvedBuildDir 'egolink_call010_audio_loop.bin'
    $bootloaderImage = Join-Path $resolvedBuildDir 'bootloader\bootloader.bin'
    $partitionImage = Join-Path $resolvedBuildDir 'partition_table\partition-table.bin'
    $sdkconfigPath = Join-Path $resolvedBuildDir 'sdkconfig'
    foreach ($requiredFile in @(
            $appImage,
            $bootloaderImage,
            $partitionImage,
            $sdkconfigPath
        )) {
        if (-not (Test-Path -LiteralPath $requiredFile)) {
            throw "Missing output-diagnostic build artifact: $requiredFile"
        }
    }

    $sdkconfigText = Get-Content -LiteralPath $sdkconfigPath -Raw
    if ($sdkconfigText -notmatch '(?m)^CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN=y\s*$' -or
        $sdkconfigText -notmatch '(?m)^CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC=y\s*$') {
        throw 'Build sdkconfig is not the authorized output-only diagnostic profile.'
    }

    $actualAppSha256 = (
        Get-FileHash -LiteralPath $appImage -Algorithm SHA256
    ).Hash
    if ($actualAppSha256 -ne $ExpectedAppSha256.ToUpperInvariant()) {
        throw "Output-diagnostic image SHA-256 mismatch: expected $ExpectedAppSha256, got $actualAppSha256"
    }
    $bootloaderSha256 = (
        Get-FileHash -LiteralPath $bootloaderImage -Algorithm SHA256
    ).Hash
    $partitionSha256 = (
        Get-FileHash -LiteralPath $partitionImage -Algorithm SHA256
    ).Hash
    $gitCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to resolve repository commit.'
    }
    $firmwareStatus = @(& git -C $repoRoot status --porcelain -- firmware/audio_loop)

    $manifest = [ordered]@{
        task_id = 'CALL-010'
        run_id = $RunId
        mode = 'output_only_staged_diagnostic'
        operator_authorized = $true
        authorization_scope = 'wearable only; bounded staged higher-volume speaker diagnostic; no microphone capture; no raw audio retention; do not touch 4G board'
        authorization_source = 'operator message on 2026-09-02: requested another higher-volume test'
        started_at = $startedAt.ToString('o')
        board_id = 'wearable-node-001'
        board_family = 'ESP32-S3-Touch-AMOLED-2.06'
        physical_pcb_revision = 'unknown'
        enclosure_state = 'complete_enclosure_operator_confirmed'
        speaker_opening_visual = 'visible_in_operator_photo'
        speaker_transducer_and_contact = 'unverified'
        serial_port = $Port
        port_pnp_instance_id = $portDevice.InstanceId
        usb_composite_instance_id = $matchingCompositeDevices[0].InstanceId
        expected_mac = $expectedMac
        connection_path = 'USB Serial/JTAG data cable; USB-attached engineering run'
        repository_commit = $gitCommit
        firmware_worktree_dirty = $firmwareStatus.Count -gt 0
        esp_idf_path = $env:IDF_PATH
        esp_idf_python = $idfPython
        build_dir = $resolvedBuildDir
        images = [ordered]@{
            application = [ordered]@{
                path = $appImage
                size_bytes = (Get-Item -LiteralPath $appImage).Length
                sha256 = $actualAppSha256
            }
            bootloader = [ordered]@{
                path = $bootloaderImage
                size_bytes = (Get-Item -LiteralPath $bootloaderImage).Length
                sha256 = $bootloaderSha256
            }
            partition_table = [ordered]@{
                path = $partitionImage
                size_bytes = (Get-Item -LiteralPath $partitionImage).Length
                sha256 = $partitionSha256
            }
        }
        no_audio_storage = $true
        microphone_constructed = $false
        rx_channel_created = $false
        configured_output = [ordered]@{
            countdown_seconds = $expectedCountdown
            frequency_hz = $expectedFrequencyHz
            pcm_peak = $expectedPcmPeak
            tone_seconds_per_stage = $expectedToneSeconds
            muted_gap_seconds = $expectedGapSeconds
            stages = $expectedStages
            maximum_volume = 85
        }
        operator_safety_setup = [ordered]@{
            device_on_stable_surface = 'operator_instruction_required'
            speaker_opening_uncovered = 'operator_instruction_required'
            minimum_distance_from_ear_m = 1
            stop_if_painful_or_abnormally_distorted = $true
        }
        controlled_start = 'esptool --after no_reset; open serial; one RTS reset pulse'
        capture_timeout_seconds = $CaptureTimeoutSeconds
        automatic_restore_performed_by_this_runner = $false
        post_run_restore_required = $true
        intended_post_run_image = 'UI-001'
    }
    Write-JsonEvidence -Path $manifestPath -Value $manifest

    $identity = Invoke-CapturedNative `
        -FilePath $idfPython `
        -ArgumentList @('-m', 'esptool', '--port', $Port, 'chip_id') `
        -LogPath $chipLog
    if ($identity.exit_code -ne 0) {
        throw "Read-only chip identity failed; see $chipLog"
    }
    if ($identity.text -notmatch 'ESP32-S3') {
        throw "Read-only chip identity did not report ESP32-S3; see $chipLog"
    }
    if ($identity.text -notmatch [regex]::Escape($expectedMac)) {
        throw "Chip MAC does not match wearable-node-001; see $chipLog"
    }

    Push-Location $resolvedBuildDir
    try {
        $operatorFlashStarted = $true
        $flash = Invoke-CapturedNative `
            -FilePath $idfPython `
            -ArgumentList @(
                '-m', 'esptool', '--chip', 'esp32s3', '-p', $Port,
                '-b', '460800', '--before', 'default_reset', '--after',
                'no_reset', 'write_flash', '--flash_mode', 'dio',
                '--flash_freq', '80m', '--flash_size', '16MB',
                '0x0', 'bootloader/bootloader.bin',
                '0x10000', 'egolink_call010_audio_loop.bin',
                '0x8000', 'partition_table/partition-table.bin'
            ) `
            -LogPath $flashLog
    } finally {
        Pop-Location
    }
    if ($flash.exit_code -ne 0) {
        throw "Output-diagnostic flash failed; see $flashLog"
    }
    $verifiedFlashRegions = [regex]::Matches(
        $flash.text,
        'Hash of data verified\.',
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    ).Count
    if ($verifiedFlashRegions -ne 3) {
        throw "Expected three verified flash regions, observed $verifiedFlashRegions; see $flashLog"
    }

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
        $serial.Dispose()
        throw "Unable to open $Port for bounded serial evidence."
    }

    $sequenceComplete = $false
    $captureStartedAt = [DateTimeOffset]::Now
    $captureDeadline = $captureStartedAt.AddSeconds($CaptureTimeoutSeconds)
    $writer = [System.IO.StreamWriter]::new(
        $serialLog,
        $false,
        [System.Text.UTF8Encoding]::new($false)
    )
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
                $line = $serial.ReadLine().Replace("`0", '').TrimEnd("`r")
                $record = '{0} {1}' -f (
                    [DateTimeOffset]::Now.ToString('o')
                ), $line
                $writer.WriteLine($record)
                $writer.Flush()
                Write-Host $record
                if ($line.Contains(
                        'AUDIO_SEQUENCE_COMPLETE result=ESP_OK speaker_pa_off_verified=true deadline_expired=false mode=output_diagnostic'
                    )) {
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
        (Get-Content -LiteralPath $serialLog -Raw).Replace("`0", '')
    } else {
        ''
    }
    $checks = [ordered]@{}
    $checks.armed = Test-ContainsLiteral -Text $serialText -Literal (
        'AUDIO_OUTPUT_DIAGNOSTIC_ARMED countdown_seconds=15 stage_count=3 ' +
        'microphone_constructed=false rx_channel_created=false ' +
        'no_audio_storage=true'
    )

    $countdownValues = @(
        [regex]::Matches(
            $serialText,
            'AUDIO_OUTPUT_COUNTDOWN remaining_seconds=(\d+) speaker_muted=true speaker_pa_off_verified=true'
        ) | ForEach-Object { [int]$_.Groups[1].Value }
    )
    $expectedCountdownValues = @($expectedCountdown..1)
    $checks.countdown_complete = (
        ($countdownValues -join ',') -eq ($expectedCountdownValues -join ',')
    )

    $stageChecks = @()
    foreach ($stageDefinition in $expectedStages) {
        $stage = $stageDefinition.stage
        $volume = $stageDefinition.volume
        $register = $stageDefinition.register
        $startMarker = (
            "AUDIO_OUTPUT_STAGE_START stage=$stage volume=$volume " +
            "expected_reg32=$register actual_reg32=$register " +
            "frequency_hz=$expectedFrequencyHz pcm_peak=$expectedPcmPeak " +
            "seconds=$expectedToneSeconds expected_frames=$expectedFrames " +
            "bytes_per_frame=$expectedBytesPerFrame " +
            "expected_bytes=$expectedBytesPerStage"
        )
        $endMarker = (
            "AUDIO_OUTPUT_STAGE_END stage=$stage volume=$volume " +
            "actual_reg32=$register attempted_frames=$expectedFrames " +
            "successful_frames=$expectedFrames " +
            "requested_bytes=$expectedBytesPerStage " +
            "actual_bytes_written=$expectedBytesPerStage short_writes=0 " +
            'write_errors=0 speaker_muted=true ' +
            'speaker_pa_off_verified=true result=ESP_OK'
        )
        $stageResult = [ordered]@{
            stage = $stage
            volume = $volume
            expected_reg32 = $register
            start_seen = Test-ContainsLiteral -Text $serialText -Literal $startMarker
            end_seen = Test-ContainsLiteral -Text $serialText -Literal $endMarker
            operator_audible_confirmation = 'pending'
            operator_quality_confirmation = 'pending'
        }
        $stageChecks += $stageResult
        $checks["stage_${stage}_start"] = $stageResult.start_seen
        $checks["stage_${stage}_end"] = $stageResult.end_seen
    }

    foreach ($afterStage in @(1, 2)) {
        $checks["gap_after_stage_$afterStage"] = Test-ContainsLiteral `
            -Text $serialText `
            -Literal (
                "AUDIO_OUTPUT_STAGE_GAP after_stage=$afterStage " +
                "seconds=$expectedGapSeconds speaker_muted=true " +
                'speaker_pa_off_verified=true'
            )
    }
    $checks.diagnostic_complete = Test-ContainsLiteral `
        -Text $serialText `
        -Literal (
            'AUDIO_OUTPUT_DIAGNOSTIC_COMPLETE result=ESP_OK ' +
            'completed_stages=3 microphone_reads=0 raw_audio_retained=false ' +
            'speaker_pa_off_verified=true deadline_expired=false'
        )
    $checks.final_safe = Test-ContainsLiteral `
        -Text $serialText `
        -Literal (
            'AUDIO_SEQUENCE_COMPLETE result=ESP_OK ' +
            'speaker_pa_off_verified=true deadline_expired=false ' +
            'mode=output_diagnostic'
        )
    $checks.no_microphone_phase = (
        -not $serialText.Contains('AUDIO_PHASE_START phase=input_metrics') -and
        -not $serialText.Contains('AUDIO_PHASE_START phase=attenuated_local_loop') -and
        -not $serialText.Contains('AUDIO_CHANNEL_METRICS')
    )

    $fatalPattern = 'Guru Meditation|Brownout|watchdog|abort\(\)|assert failed|LoadProhibited|StoreProhibited'
    $fatalMarkers = @(
        [regex]::Matches(
            $serialText,
            $fatalPattern,
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        ) | ForEach-Object { $_.Value } | Select-Object -Unique
    )
    $errorLevelLines = @(
        $serialText -split "`r?`n" |
            Where-Object { $_ -match '\sE \(\d+\)\s' }
    )
    $allChecksPassed = -not ($checks.Values -contains $false)
    $passed = (
        $sequenceComplete -and
        $allChecksPassed -and
        $fatalMarkers.Count -eq 0 -and
        $errorLevelLines.Count -eq 0
    )
    $finishedAt = [DateTimeOffset]::Now
    $summary = [ordered]@{
        task_id = 'CALL-010'
        run_id = $RunId
        mode = 'output_only_staged_diagnostic'
        result = if ($passed) { 'PASS_LOGICAL_RUNTIME' } else { 'FAIL_OR_INCOMPLETE' }
        acoustic_result = 'PENDING_OPERATOR_CONFIRMATION'
        started_at = $startedAt.ToString('o')
        capture_started_at = $captureStartedAt.ToString('o')
        finished_at = $finishedAt.ToString('o')
        board = [ordered]@{
            board_id = 'wearable-node-001'
            board_family = 'ESP32-S3-Touch-AMOLED-2.06'
            physical_pcb_revision = 'unknown'
            enclosure_state = 'complete_enclosure_operator_confirmed'
            serial_port = $Port
            usb_identity = 'VID_303A/PID_1001'
            mac = $expectedMac
        }
        operator_image = [ordered]@{
            path = $appImage
            size_bytes = (Get-Item -LiteralPath $appImage).Length
            sha256 = $actualAppSha256
            flash_started = $operatorFlashStarted
            flash_completed = $flash.exit_code -eq 0
            flash_hashes_verified = $verifiedFlashRegions -eq 3
            controlled_start = 'esptool --after no_reset; serial opened before one RTS reset pulse'
        }
        runtime = [ordered]@{
            sequence_complete_seen = $sequenceComplete
            checks = $checks
            stages = $stageChecks
            countdown_values_seen = $countdownValues
            fatal_markers = $fatalMarkers
            error_level_lines = $errorLevelLines
            microphone_constructed = $false
            microphone_reads = 0
            raw_audio_retained = $false
            final_speaker_pa_off_verified = $checks.final_safe
            deadline_expired = -not $checks.final_safe
        }
        privacy_and_scope = [ordered]@{
            raw_audio_retained = $false
            microphone_capture_performed = $false
            connectivity_board_targeted = $false
            audible_output_operator_confirmation = 'pending'
        }
        post_run_restore = [ordered]@{
            performed_by_this_runner = $false
            status = 'REQUIRED_EXTERNAL_STEP'
            intended_image = 'UI-001'
            warning = 'Caller must restore in a finally path even when this runner throws.'
        }
        final_board_state_after_this_runner = 'CALL-010 output-diagnostic image remains installed; PA-off is verified only if final_safe=true; UI-001 restore is required'
        non_claims = @(
            'PASS_LOGICAL_RUNTIME does not prove audible output without operator confirmation.',
            'This output-only diagnostic provides no microphone or full-duplex evidence.',
            'No SPL, hearing-safety, distortion, AEC/AGC, product-power, LTE/RTC or P0-CALL PASS claim.',
            'This runner does not restore UI-001; restoration evidence belongs to the caller orchestration.'
        )
        evidence = [ordered]@{
            manifest = $manifestPath
            chip_identity = $chipLog
            flash = $flashLog
            serial = $serialLog
            result = $summaryPath
            report = $reportPath
        }
    }
    Write-JsonEvidence -Path $summaryPath -Value $summary

    $report = @"
# CALL-010 Staged Output Diagnostic

- Run: $RunId
- Logical result: $($summary.result)
- Acoustic result: pending operator confirmation
- Board: wearable-node-001 / ESP32-S3-Touch-AMOLED-2.06
- Connection: $Port, USB VID_303A/PID_1001, MAC $expectedMac
- Mode: output-only; microphone constructed/read: false/0
- Output ladder: volume 55, 70, 85; 2 seconds each; 2-second muted gaps
- Tone: 1 kHz, PCM peak 5000; raw audio retained: false
- Sequence complete marker: $sequenceComplete
- Final PA-off marker: $($checks.final_safe)
- Fatal markers: $($fatalMarkers -join ', ')
- Error-level runtime lines: $($errorLevelLines.Count)
- 4G board targeted: false
- UI-001 restore: required external finally step; not performed by this runner

This result is bounded engineering evidence. A logical pass does not establish
audibility until the operator reports which stages were heard and whether any
stage was painful or abnormally distorted. This output-only slice does not add
microphone, duplex, SPL, product-power, LTE/RTC, or P0-CALL evidence.
"@
    Write-Utf8NoBomText -Path $reportPath -Content $report

    if (-not $passed) {
        throw "CALL-010 output diagnostic did not satisfy serial/runtime checks; see $summaryPath"
    }

    Write-Host (
        'CALL-010 output diagnostic passed logical checks. ' +
        "UI-001 restoration remains required. Evidence: $resolvedEvidenceDir"
    )
} catch {
    $failure = $_
    if (-not (Test-Path -LiteralPath $summaryPath)) {
        $finishedAt = [DateTimeOffset]::Now
        $failureSummary = [ordered]@{
            task_id = 'CALL-010'
            run_id = $RunId
            mode = 'output_only_staged_diagnostic'
            result = 'FAIL_OR_INCOMPLETE'
            acoustic_result = 'NOT_EVALUATED'
            started_at = $startedAt.ToString('o')
            capture_started_at = if ($null -eq $captureStartedAt) {
                $null
            } else {
                $captureStartedAt.ToString('o')
            }
            finished_at = $finishedAt.ToString('o')
            error = $failure.Exception.Message
            operator_flash_started = $operatorFlashStarted
            raw_audio_retained = $false
            microphone_capture_performed = $false
            connectivity_board_targeted = $false
            post_run_restore = [ordered]@{
                performed_by_this_runner = $false
                status = if ($operatorFlashStarted) {
                    'REQUIRED_EXTERNAL_STEP'
                } else {
                    'NOT_REQUIRED_NO_OPERATOR_FLASH_STARTED'
                }
                intended_image = 'UI-001'
                warning = 'Caller must restore in a finally path if any CALL image was flashed.'
            }
            evidence = [ordered]@{
                manifest = if (Test-Path -LiteralPath $manifestPath) { $manifestPath } else { $null }
                chip_identity = if (Test-Path -LiteralPath $chipLog) { $chipLog } else { $null }
                flash = if (Test-Path -LiteralPath $flashLog) { $flashLog } else { $null }
                serial = if (Test-Path -LiteralPath $serialLog) { $serialLog } else { $null }
            }
        }
        Write-JsonEvidence -Path $summaryPath -Value $failureSummary
        $failureReport = @"
# CALL-010 Staged Output Diagnostic

- Run: $RunId
- Result: FAIL_OR_INCOMPLETE
- Error: $($failure.Exception.Message)
- Operator flash started: $operatorFlashStarted
- Raw audio retained: false
- Microphone capture performed: false
- 4G board targeted: false
- UI-001 restore: $(if ($operatorFlashStarted) { 'required external finally step' } else { 'not required; operator flash did not start' })

This runner does not perform or claim UI-001 restoration.
"@
        Write-Utf8NoBomText -Path $reportPath -Content $failureReport
    }
    throw
}
