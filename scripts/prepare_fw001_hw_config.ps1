param(
    [string]$HostName = $env:EGOLINK_VPS_HOST,
    [int]$Port = 8790,
    [ValidateSet("http", "https")]
    [string]$Scheme = "http",
    [string]$DeviceId = "ego-link-r1-connectivity-001",
    [string]$FwVersion = "0.1.0-fw001-hw-r1",
    [string]$TestRunId = $("fw001-hw-r1-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$Token = $env:EGOLINK_MESSAGE_HUB_TOKEN,
    [string]$TokenFile = "server/runtime/vps_message_hub_token.txt",
    [string]$FirmwareDir = "firmware/mqtt_heartbeat",
    [string]$ConfigPath = "",
    [string]$SourceSdkconfig = "",
    [string]$WifiSsid = "",
    [string]$WifiPassword = "",
    [string]$BuildDir = "build_fw001_hw",
    [string]$IdfExport = "C:\Espressif\v5.4.2\esp-idf\export.ps1",
    [switch]$EnableSim7670Gnss,
    [switch]$EnableSim7670LteStatus,
    [switch]$EnableSim7670LteHttpProbe,
    [switch]$EnableSim7670LteHttpCommandLoop,
    [switch]$EnableSim7670LocationObservation,
    [switch]$EnableD1PeriodicLocation,
    [int]$D1PeriodicLocationIntervalSec = 60,
    [switch]$EnableRawPostFailOnceTest,
    [switch]$EnableReconnectStoreForwardTest,
    [switch]$EnableMax17048Power,
    [switch]$EnableQmi8658Imu,
    [int]$Sim7670UartNum = 1,
    [int]$Sim7670UartRxGpio = 17,
    [int]$Sim7670UartTxGpio = 18,
    [int]$Sim7670UartBaud = 115200,
    [int]$Max17048I2CPort = 0,
    [int]$Max17048SdaGpio = 15,
    [int]$Max17048SclGpio = 16,
    [int]$Qmi8658I2CPort = 0,
    [int]$Qmi8658SdaGpio = 15,
    [int]$Qmi8658SclGpio = 16,
    [int]$Qmi8658I2CAddress = 107,
    [int]$Qmi8658I2CTimeoutMs = 1000,
    [int]$Qmi8658SampleIntervalMs = 50,
    [int]$Qmi8658BootSampleCount = 0,
    [switch]$Build,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathValue))
}

function ConvertTo-KconfigString {
    param([string]$Value)
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

function Read-SdkconfigString {
    param(
        [string]$PathValue,
        [string]$Key
    )
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        return ""
    }
    $pattern = "^$([regex]::Escape($Key))=(.*)$"
    foreach ($line in Get-Content -LiteralPath $PathValue) {
        if ($line -match $pattern) {
            $raw = $Matches[1].Trim()
            if ($raw.StartsWith('"') -and $raw.EndsWith('"') -and $raw.Length -ge 2) {
                return $raw.Substring(1, $raw.Length - 2)
            }
            return $raw
        }
    }
    return ""
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$firmwarePath = Resolve-RepoPath $FirmwareDir
if (-not (Test-Path -LiteralPath $firmwarePath -PathType Container)) {
    throw "FirmwareDir not found: $firmwarePath"
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $firmwarePath "sdkconfig.vps.local"
}
$resolvedConfigPath = Resolve-RepoPath $ConfigPath
if ([System.IO.Path]::GetFileName($resolvedConfigPath) -notmatch "^sdkconfig\..*\.local$") {
    throw "ConfigPath must be an ignored local sdkconfig file such as sdkconfig.vps.local."
}

if (-not $SourceSdkconfig) {
    $SourceSdkconfig = Join-Path $firmwarePath "sdkconfig"
}
$resolvedSourceSdkconfig = Resolve-RepoPath $SourceSdkconfig

if (-not $HostName) {
    throw "HostName is required. Pass -HostName or set EGOLINK_VPS_HOST."
}

$tokenSource = "parameter"
if (-not $Token) {
    $resolvedTokenFile = Resolve-RepoPath $TokenFile
    if (Test-Path -LiteralPath $resolvedTokenFile -PathType Leaf) {
        $Token = (Get-Content -LiteralPath $resolvedTokenFile -Raw).Trim()
        $tokenSource = "token_file"
    } else {
        $tokenSource = "missing"
    }
}
if (-not $Token) {
    throw "Message Hub token is required. Pass -Token, set EGOLINK_MESSAGE_HUB_TOKEN, or provide the ignored token file."
}
if ($EnableD1PeriodicLocation -and ($D1PeriodicLocationIntervalSec -lt 15 -or $D1PeriodicLocationIntervalSec -gt 3600)) {
    throw "D1PeriodicLocationIntervalSec must be between 15 and 3600 seconds."
}
if ($EnableQmi8658Imu -and $Qmi8658I2CAddress -notin @(106, 107)) {
    throw "Qmi8658I2CAddress must be decimal 106 (0x6A) or 107 (0x6B)."
}
if ($EnableQmi8658Imu -and ($Qmi8658SampleIntervalMs -lt 1 -or $Qmi8658SampleIntervalMs -gt 1000)) {
    throw "Qmi8658SampleIntervalMs must be between 1 and 1000."
}
if ($EnableQmi8658Imu -and ($Qmi8658I2CTimeoutMs -lt 10 -or $Qmi8658I2CTimeoutMs -gt 5000)) {
    throw "Qmi8658I2CTimeoutMs must be between 10 and 5000."
}
if ($EnableQmi8658Imu -and ($Qmi8658BootSampleCount -lt 0 -or $Qmi8658BootSampleCount -gt 1000)) {
    throw "Qmi8658BootSampleCount must be between 0 and 1000."
}
if ($EnableQmi8658Imu -and $EnableMax17048Power) {
    $sameI2CBus = $Qmi8658I2CPort -eq $Max17048I2CPort -and
        $Qmi8658SdaGpio -eq $Max17048SdaGpio -and
        $Qmi8658SclGpio -eq $Max17048SclGpio
    if (-not $sameI2CBus) {
        throw "QMI8658 and MAX17048 must use the same I2C port/SDA/SCL when enabled together."
    }
}

$effectiveEnableSim7670LocationObservation = [bool]($EnableSim7670LocationObservation -or $EnableReconnectStoreForwardTest)
$effectiveEnableSim7670LocationObservation = [bool]($effectiveEnableSim7670LocationObservation -or $EnableD1PeriodicLocation)
$effectiveEnableSim7670LteHttpCommandLoop = [bool]($EnableSim7670LteHttpCommandLoop -or $effectiveEnableSim7670LocationObservation -or $EnableD1PeriodicLocation)
$effectiveEnableSim7670LteStatus = [bool]($EnableSim7670LteStatus -or $EnableSim7670LteHttpProbe -or $effectiveEnableSim7670LteHttpCommandLoop)

$wifiSource = "parameters"
if (-not $WifiSsid) {
    $WifiSsid = Read-SdkconfigString $resolvedSourceSdkconfig "CONFIG_EGOLINK_WIFI_SSID"
    $wifiSource = "source_sdkconfig"
}
if (-not $WifiPassword) {
    $WifiPassword = Read-SdkconfigString $resolvedSourceSdkconfig "CONFIG_EGOLINK_WIFI_PASSWORD"
}

$baseUrl = "${Scheme}://${HostName}:${Port}"
$lines = @(
    "# Generated by scripts/prepare_fw001_hw_config.ps1",
    "# Local runtime config for FW-001-HW. Do not commit this file.",
    "CONFIG_EGOLINK_MESSAGE_HUB_HTTP_ENABLED=y",
    "CONFIG_EGOLINK_MESSAGE_HUB_BASE_URL=$(ConvertTo-KconfigString $baseUrl)",
    "CONFIG_EGOLINK_MESSAGE_HUB_BEARER_TOKEN=$(ConvertTo-KconfigString $Token)",
    "CONFIG_EGOLINK_DEVICE_ID=$(ConvertTo-KconfigString $DeviceId)",
    "CONFIG_EGOLINK_FW_VERSION=$(ConvertTo-KconfigString $FwVersion)",
    "CONFIG_EGOLINK_TEST_RUN_ID=$(ConvertTo-KconfigString $TestRunId)",
    "CONFIG_EGOLINK_HEARTBEAT_INTERVAL_SEC=10",
    "CONFIG_EGOLINK_SENSOR_EVENT_INTERVAL_SEC=30",
    "CONFIG_EGOLINK_MESSAGE_HUB_COMMAND_POLL_INTERVAL_SEC=5"
)
if ($EnableSim7670Gnss) {
    $lines += "CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_GNSS_ENABLED is not set"
}
if ($effectiveEnableSim7670LteStatus) {
    $lines += "CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED is not set"
}
if ($EnableSim7670LteHttpProbe) {
    $lines += "CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_ENABLED is not set"
}
if ($effectiveEnableSim7670LteHttpCommandLoop) {
    $lines += "CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED is not set"
}
if ($effectiveEnableSim7670LocationObservation) {
    $lines += "CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED is not set"
}
if ($EnableD1PeriodicLocation) {
    $lines += @(
        "CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED=y",
        "CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_INTERVAL_SEC=$D1PeriodicLocationIntervalSec"
    )
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_D1_PERIODIC_LOCATION_ENABLED is not set"
}
if ($EnableRawPostFailOnceTest) {
    $lines += "CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST is not set"
}
if ($EnableReconnectStoreForwardTest) {
    $lines += "CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST=y"
} else {
    $lines += "# CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST is not set"
}
if ($EnableMax17048Power) {
    $lines += @(
        "# CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MOCK is not set",
        "CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048=y",
        "CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_I2C_PORT=$Max17048I2CPort",
        "CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_SDA_GPIO=$Max17048SdaGpio",
        "CONFIG_EGOLINK_PLATFORM_POWER_MAX17048_SCL_GPIO=$Max17048SclGpio"
    )
} else {
    $lines += @(
        "CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MOCK=y",
        "# CONFIG_EGOLINK_PLATFORM_POWER_BACKEND_MAX17048 is not set"
    )
}
if ($EnableQmi8658Imu) {
    $lines += @(
        "# CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK is not set",
        "CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658=y",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_PORT=$Qmi8658I2CPort",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SDA_GPIO=$Qmi8658SdaGpio",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SCL_GPIO=$Qmi8658SclGpio",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_ADDR=$Qmi8658I2CAddress",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_I2C_TIMEOUT_MS=$Qmi8658I2CTimeoutMs",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_WHOAMI_EXPECTED=5",
        "CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_SAMPLE_INTERVAL_MS=$Qmi8658SampleIntervalMs",
        "# CONFIG_EGOLINK_PLATFORM_IMU_QMI8658_AXP2101_RAILS is not set",
        "CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT=$Qmi8658BootSampleCount",
        "CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_INTERVAL_MS=$Qmi8658SampleIntervalMs"
    )
} else {
    $lines += @(
        "CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y",
        "# CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658 is not set",
        "CONFIG_EGOLINK_PLATFORM_IMU_BOOT_SAMPLE_COUNT=0"
    )
}
if ($EnableSim7670Gnss -or $effectiveEnableSim7670LteStatus -or $EnableSim7670LteHttpProbe -or $effectiveEnableSim7670LteHttpCommandLoop -or $effectiveEnableSim7670LocationObservation) {
    $lines += @(
        "CONFIG_EGOLINK_SIM7670_UART_NUM=$Sim7670UartNum",
        "CONFIG_EGOLINK_SIM7670_UART_RX_GPIO=$Sim7670UartRxGpio",
        "CONFIG_EGOLINK_SIM7670_UART_TX_GPIO=$Sim7670UartTxGpio",
        "CONFIG_EGOLINK_SIM7670_UART_BAUD=$Sim7670UartBaud"
    )
}
if ($WifiSsid) {
    $lines += "CONFIG_EGOLINK_WIFI_SSID=$(ConvertTo-KconfigString $WifiSsid)"
}
if ($WifiPassword) {
    $lines += "CONFIG_EGOLINK_WIFI_PASSWORD=$(ConvertTo-KconfigString $WifiPassword)"
}

New-Item -ItemType Directory -Force -Path (Split-Path $resolvedConfigPath -Parent) | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($resolvedConfigPath, [string[]]$lines, $utf8NoBom)

$configLeaf = [System.IO.Path]::GetFileName($resolvedConfigPath)
$sdkconfigDefaults = "sdkconfig.defaults;$configLeaf"
$buildCommand = ". $IdfExport; idf.py -B $BuildDir -D `"SDKCONFIG=$BuildDir/sdkconfig`" -D `"SDKCONFIG_DEFAULTS=$sdkconfigDefaults`" build"

if ($Build) {
    if ((Split-Path $resolvedConfigPath -Parent) -ne $firmwarePath) {
        throw "Build requires ConfigPath to be inside FirmwareDir so SDKCONFIG_DEFAULTS can reference it."
    }
    if (-not (Test-Path -LiteralPath $IdfExport -PathType Leaf)) {
        throw "ESP-IDF export script not found: $IdfExport"
    }
    Push-Location $firmwarePath
    try {
        $buildSdkconfig = Join-Path $BuildDir "sdkconfig"
        if (Test-Path -LiteralPath $buildSdkconfig -PathType Leaf) {
            Remove-Item -LiteralPath $buildSdkconfig -Force
        }
        . $IdfExport
        & idf.py -B $BuildDir -D "SDKCONFIG=$BuildDir/sdkconfig" -D "SDKCONFIG_DEFAULTS=$sdkconfigDefaults" build
        if ($LASTEXITCODE -ne 0) {
            throw "idf.py build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

$result = [pscustomobject]@{
    ok = $true
    config_path = $resolvedConfigPath
    firmware_dir = $firmwarePath
    build_dir = (Join-Path $firmwarePath $BuildDir)
    device_id = $DeviceId
    fw_version = $FwVersion
    test_run_id = $TestRunId
    base_url = $baseUrl
    token_source = $tokenSource
    wifi_source = $wifiSource
    sim7670_gnss_enabled = [bool]$EnableSim7670Gnss
    sim7670_lte_status_enabled = [bool]$effectiveEnableSim7670LteStatus
    sim7670_lte_http_probe_enabled = [bool]$EnableSim7670LteHttpProbe
    sim7670_lte_http_command_loop_enabled = [bool]$effectiveEnableSim7670LteHttpCommandLoop
    sim7670_location_observation_enabled = [bool]$effectiveEnableSim7670LocationObservation
    d1_periodic_location_enabled = [bool]$EnableD1PeriodicLocation
    d1_periodic_location_interval_sec = $D1PeriodicLocationIntervalSec
    raw_post_fail_once_test_enabled = [bool]$EnableRawPostFailOnceTest
    reconnect_store_forward_test_enabled = [bool]$EnableReconnectStoreForwardTest
    max17048_power_enabled = [bool]$EnableMax17048Power
    max17048_i2c_port = $Max17048I2CPort
    max17048_sda_gpio = $Max17048SdaGpio
    max17048_scl_gpio = $Max17048SclGpio
    qmi8658_imu_enabled = [bool]$EnableQmi8658Imu
    qmi8658_i2c_port = $Qmi8658I2CPort
    qmi8658_sda_gpio = $Qmi8658SdaGpio
    qmi8658_scl_gpio = $Qmi8658SclGpio
    qmi8658_i2c_address = $Qmi8658I2CAddress
    qmi8658_i2c_timeout_ms = $Qmi8658I2CTimeoutMs
    qmi8658_sample_interval_ms = $Qmi8658SampleIntervalMs
    qmi8658_boot_sample_count = $Qmi8658BootSampleCount
    qmi8658_axp2101_rails_enabled = $false
    build_command = $buildCommand
    flash_intentionally_not_run = $true
}

if ($Json) {
    $result | ConvertTo-Json -Depth 4
} else {
    Write-Host "Prepared FW-001-HW local config: $resolvedConfigPath"
    Write-Host "Device ID: $DeviceId"
    Write-Host "Test run ID: $TestRunId"
    Write-Host "Build command:"
    Write-Host "  $buildCommand"
    Write-Host "Flash intentionally not run by this script."
}
