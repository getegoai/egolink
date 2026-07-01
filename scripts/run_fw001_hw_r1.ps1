param(
    [string]$HostName = $env:EGOLINK_VPS_HOST,
    [int]$Port = 8790,
    [ValidateSet("http", "https")]
    [string]$Scheme = "http",
    [string]$DeviceId = "ego-link-r1-connectivity-001",
    [string]$FwVersion = "0.1.0-fw001-hw-r1",
    [string]$TestRunId = $("fw001-hw-r1-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$TokenFile = "server/runtime/vps_message_hub_token.txt",
    [string]$FirmwareDir = "firmware/mqtt_heartbeat",
    [string]$BuildDir = "build_fw001_hw",
    [string]$IdfExport = "C:\Espressif\v5.4.2\esp-idf\export.ps1",
    [string]$FlashPort = "",
    [string]$ExistingCommandId = "",
    [string]$ExpectedAckTestRunId = "",
    [string]$ExpectedMessageTestRunId = "",
    [ValidateSet("command-created", "validator-start", "test-run-created")]
    [string]$LteEvidenceSince = "command-created",
    [string]$LteCommandName = "set_report_interval",
    [int]$ValidationTimeoutSec = 180,
    [int]$ValidationPollIntervalSec = 5,
    [switch]$EnableSim7670Gnss,
    [switch]$EnableSim7670LteStatus,
    [switch]$EnableSim7670LteHttpProbe,
    [switch]$EnableSim7670LteHttpCommandLoop,
    [switch]$EnableSim7670LocationObservation,
    [switch]$EnableRawPostFailOnceTest,
    [switch]$PrepareBuild,
    [switch]$Flash,
    [switch]$IUnderstandFlashWritesFirmware,
    [switch]$Validate,
    [switch]$ArmLteCommandOnly,
    [switch]$OperatorConfirmedIndependentPower,
    [switch]$OperatorConfirmedUsbDisconnected,
    [switch]$RequireLteLocationReport,
    [switch]$RequireLteLocationObservation,
    [switch]$RequireLocationFix,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Resolve-RepoPath {
    param([string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathValue))
}

function Add-If {
    param(
        [System.Collections.Generic.List[string]]$List,
        [bool]$Condition,
        [string]$Value
    )
    if ($Condition) {
        $List.Add($Value)
    }
}

function ConvertFrom-LastJsonObject {
    param([object[]]$OutputLines)
    $lines = @($OutputLines | ForEach-Object { [string]$_ })
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        if ($lines[$i].Trim() -eq "{") {
            return (($lines[$i..($lines.Count - 1)] -join "`n") | ConvertFrom-Json)
        }
    }
    throw "No JSON object found in command output."
}

$firmwarePath = Resolve-RepoPath $FirmwareDir
$hubUrl = "${Scheme}://${HostName}:${Port}"
$prepareScript = Resolve-RepoPath "scripts/prepare_fw001_hw_config.ps1"
$validationScript = Resolve-RepoPath "scripts/validate_fw001_hw_loop.py"
$lteHttpValidationScript = Resolve-RepoPath "scripts/validate_lte_http_probe.py"
$lteCommandValidationScript = Resolve-RepoPath "scripts/validate_lte_command_loop.py"
$tokenPath = Resolve-RepoPath $TokenFile
$buildPath = Join-Path $firmwarePath $BuildDir
$binaryPath = Join-Path $buildPath "egolink_mqtt_heartbeat.bin"
$effectiveEnableSim7670LteHttpCommandLoop = [bool]($EnableSim7670LteHttpCommandLoop -or $EnableSim7670LocationObservation)
$effectiveEnableSim7670LteStatus = [bool]($EnableSim7670LteStatus -or $EnableSim7670LteHttpProbe -or $effectiveEnableSim7670LteHttpCommandLoop)

$result = [ordered]@{
    ok = $true
    mode = "plan"
    host_name = $HostName
    hub_url = $hubUrl
    device_id = $DeviceId
    fw_version = $FwVersion
    test_run_id = $TestRunId
    sim7670_gnss_enabled = [bool]$EnableSim7670Gnss
    sim7670_lte_status_enabled = [bool]$effectiveEnableSim7670LteStatus
    sim7670_lte_http_probe_enabled = [bool]$EnableSim7670LteHttpProbe
    sim7670_lte_http_command_loop_enabled = [bool]$effectiveEnableSim7670LteHttpCommandLoop
    sim7670_location_observation_enabled = [bool]$EnableSim7670LocationObservation
    raw_post_fail_once_test_enabled = [bool]$EnableRawPostFailOnceTest
    firmware_dir = $firmwarePath
    build_dir = $buildPath
    binary_path = $binaryPath
    existing_command_id = $ExistingCommandId
    expected_ack_test_run_id = $ExpectedAckTestRunId
    expected_message_test_run_id = $ExpectedMessageTestRunId
    lte_evidence_since = $LteEvidenceSince
    lte_command_name = $LteCommandName
    require_lte_location_report = [bool]($RequireLteLocationReport -or $RequireLocationFix)
    require_lte_location_observation = [bool]$RequireLteLocationObservation
    require_location_fix = [bool]$RequireLocationFix
    prepare_build_ran = $false
    flash_ran = $false
    validate_ran = $false
    arm_lte_command_only = [bool]$ArmLteCommandOnly
    flash_guard = "requires -Flash -FlashPort <port> -IUnderstandFlashWritesFirmware"
    validation_guard = "requires -Validate -OperatorConfirmedIndependentPower -OperatorConfirmedUsbDisconnected"
}

if (-not $PrepareBuild -and -not $Flash -and -not $Validate) {
    if ($Json) {
        $result | ConvertTo-Json -Depth 4
    } else {
        Write-Host "FW-001-HW R1 guarded runner plan"
        Write-Host "  Prepare/build: add -PrepareBuild"
        Write-Host "  Flash: add -Flash -FlashPort <COMx> -IUnderstandFlashWritesFirmware"
        Write-Host "  Validate: add -Validate -OperatorConfirmedIndependentPower -OperatorConfirmedUsbDisconnected"
        Write-Host "  Test run ID: $TestRunId"
        Write-Host "  Hub URL: $hubUrl"
        Write-Host "No hardware action was run."
    }
    exit 0
}

if (-not $HostName) {
    throw "HostName is required. Pass -HostName or set EGOLINK_VPS_HOST."
}

if ($PrepareBuild) {
    $prepareArgs = [System.Collections.Generic.List[string]]::new()
    @(
        "-ExecutionPolicy", "Bypass",
        "-File", $prepareScript,
        "-HostName", $HostName,
        "-Port", [string]$Port,
        "-Scheme", $Scheme,
        "-DeviceId", $DeviceId,
        "-FwVersion", $FwVersion,
        "-TestRunId", $TestRunId,
        "-TokenFile", $tokenPath,
        "-FirmwareDir", $firmwarePath,
        "-BuildDir", $BuildDir,
        "-IdfExport", $IdfExport,
        "-Build",
        "-Json"
    ) | ForEach-Object { $prepareArgs.Add([string]$_) }
    Add-If $prepareArgs $EnableSim7670Gnss "-EnableSim7670Gnss"
    Add-If $prepareArgs $EnableSim7670LteStatus "-EnableSim7670LteStatus"
    Add-If $prepareArgs $EnableSim7670LteHttpProbe "-EnableSim7670LteHttpProbe"
    Add-If $prepareArgs $EnableSim7670LteHttpCommandLoop "-EnableSim7670LteHttpCommandLoop"
    Add-If $prepareArgs $EnableSim7670LocationObservation "-EnableSim7670LocationObservation"
    Add-If $prepareArgs $EnableRawPostFailOnceTest "-EnableRawPostFailOnceTest"
    $prepareOutput = & powershell @prepareArgs
    if ($LASTEXITCODE -ne 0) {
        throw "prepare_fw001_hw_config.ps1 failed with exit code $LASTEXITCODE"
    }
    $result["prepare_build_ran"] = $true
    $result["prepare"] = ConvertFrom-LastJsonObject $prepareOutput
}

if ($Flash) {
    if (-not $IUnderstandFlashWritesFirmware) {
        throw "Flash requires -IUnderstandFlashWritesFirmware."
    }
    if (-not $FlashPort) {
        throw "Flash requires -FlashPort <COMx>."
    }
    if (-not (Test-Path -LiteralPath $IdfExport -PathType Leaf)) {
        throw "ESP-IDF export script not found: $IdfExport"
    }
    if (-not (Test-Path -LiteralPath $binaryPath -PathType Leaf)) {
        throw "R1 build artifact not found: $binaryPath. Run -PrepareBuild first."
    }
    Push-Location $firmwarePath
    try {
        . $IdfExport
        & idf.py -B $BuildDir -p $FlashPort flash
        if ($LASTEXITCODE -ne 0) {
            throw "idf.py flash failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
    $result["flash_ran"] = $true
    $result["flash_port"] = $FlashPort
}

if ($Validate) {
    if (-not $OperatorConfirmedIndependentPower) {
        throw "Validation requires -OperatorConfirmedIndependentPower."
    }
    if (-not $OperatorConfirmedUsbDisconnected) {
        throw "Validation requires -OperatorConfirmedUsbDisconnected."
    }
    if (-not (Test-Path -LiteralPath $tokenPath -PathType Leaf)) {
        throw "Token file not found: $tokenPath"
    }
    $oldToken = $env:EGOLINK_MESSAGE_HUB_TOKEN
    $env:EGOLINK_MESSAGE_HUB_TOKEN = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
    try {
        if ($effectiveEnableSim7670LteHttpCommandLoop) {
            $validationArgs = @(
                $lteCommandValidationScript,
                "--hub", $hubUrl,
                "--device-id", $DeviceId,
                "--test-run-id", $TestRunId,
                "--expected-fw-version", $FwVersion,
                "--command", $LteCommandName,
                "--timeout-sec", [string]$ValidationTimeoutSec,
                "--poll-interval-sec", [string]$ValidationPollIntervalSec,
                "--json"
            )
            if ($ExistingCommandId) {
                $validationArgs += @("--existing-command-id", $ExistingCommandId)
            }
            if ($ExpectedAckTestRunId) {
                $validationArgs += @("--expected-ack-test-run-id", $ExpectedAckTestRunId)
            }
            if ($ExpectedMessageTestRunId) {
                $validationArgs += @("--expected-message-test-run-id", $ExpectedMessageTestRunId)
            }
            $validationArgs += @("--evidence-since", $LteEvidenceSince)
            if ($ArmLteCommandOnly) {
                $validationArgs += "--arm-only"
            }
            if ($RequireLteLocationReport -or $RequireLocationFix) {
                $validationArgs += "--require-location-report"
            }
            if ($RequireLteLocationObservation) {
                $validationArgs += "--require-location-observation"
            }
            if ($RequireLocationFix) {
                $validationArgs += "--require-fix"
            }
        } elseif ($EnableSim7670LteHttpProbe) {
            $validationArgs = @(
                $lteHttpValidationScript,
                "--hub", $hubUrl,
                "--device-id", $DeviceId,
                "--observation-id", $TestRunId,
                "--expected-fw-version", $FwVersion,
                "--expected-test-run-id", $TestRunId,
                "--timeout-sec", [string]$ValidationTimeoutSec,
                "--poll-interval-sec", [string]$ValidationPollIntervalSec,
                "--json"
            )
        } else {
            $validationArgs = @(
                $validationScript,
                "--hub", $hubUrl,
                "--device-id", $DeviceId,
                "--test-run-id", $TestRunId,
                "--timeout-sec", [string]$ValidationTimeoutSec,
                "--poll-interval-sec", [string]$ValidationPollIntervalSec,
                "--json"
            )
        }
        $validationOutput = & python @validationArgs
        if ($LASTEXITCODE -ne 0) {
            throw "validation failed with exit code $LASTEXITCODE"
        }
    } finally {
        if ($null -eq $oldToken) {
            Remove-Item Env:EGOLINK_MESSAGE_HUB_TOKEN -ErrorAction SilentlyContinue
        } else {
            $env:EGOLINK_MESSAGE_HUB_TOKEN = $oldToken
        }
    }
    $result["validate_ran"] = $true
    $result["validation"] = $validationOutput | ConvertFrom-Json
}

$result["mode"] = "run"
if ($Json) {
    $result | ConvertTo-Json -Depth 8
} else {
    Write-Host "FW-001-HW R1 runner complete"
    Write-Host "  Prepare/build ran: $($result["prepare_build_ran"])"
    Write-Host "  Flash ran: $($result["flash_ran"])"
    Write-Host "  Validate ran: $($result["validate_ran"])"
    Write-Host "  Test run ID: $TestRunId"
}
