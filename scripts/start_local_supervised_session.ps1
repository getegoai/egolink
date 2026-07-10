param(
    [string]$BrokerIp = "",
    [int]$BrokerPort = 1883,
    [string]$DashboardHost = "127.0.0.1",
    [int]$DashboardPort = 8787,
    [int]$SafetyProcessLimit = 20,
    [int]$MaxMessages = 0,
    [int]$WaitSeconds = 0,
    [int]$SummaryLimit = 40,
    [switch]$RestartBroker,
    [switch]$RestartDashboard,
    [switch]$NoBroker,
    [switch]$NoDashboard,
    [switch]$NoWorker,
    [switch]$NoRecorder,
    [switch]$NoQualityGate,
    [switch]$Watch,
    [int]$WatchIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot "pc_simulator\runtime"
$SessionId = Get-Date -Format "yyyyMMdd-HHmmss"
$SessionDir = Join-Path $RuntimeDir "sessions\$SessionId"
$EventLog = Join-Path $RuntimeDir "events.jsonl"

function Write-SessionLine {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath (Join-Path $SessionDir "session.log") -Value $line -Encoding UTF8
}

function Get-PreferredBrokerIp {
    $candidate = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.AddressState -eq "Preferred" } |
        Sort-Object { if ($_.InterfaceAlias -eq "WLAN") { 0 } else { 1 } }, InterfaceAlias |
        Select-Object -First 1
    if (-not $candidate) {
        throw "No preferred non-loopback IPv4 address found."
    }
    return $candidate.IPAddress
}

function Get-ListenerPid {
    param(
        [string]$LocalAddress,
        [int]$Port
    )
    $connection = Get-NetTCPConnection -LocalAddress $LocalAddress -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection) {
        return [int]$connection.OwningProcess
    }
    return $null
}

function Write-SessionSummary {
    param(
        [int]$DashboardPid = 0,
        [int]$WorkerPid = 0
    )
    $summaryArgs = @(
        "scripts\local_session_summary.py",
        "--event-log", $EventLog,
        "--limit", $SummaryLimit,
        "--session-dir", $SessionDir,
        "--dashboard-url", "http://$DashboardHost`:$DashboardPort",
        "--broker", "$BrokerIp`:$BrokerPort"
    )
    if ($DashboardPid -gt 0) {
        $summaryArgs += @("--dashboard-pid", $DashboardPid)
    }
    if ($WorkerPid -gt 0) {
        $summaryArgs += @("--worker-pid", $WorkerPid)
    }
    & python @summaryArgs | Out-Null
}

function Write-SessionRecording {
    $recordingDir = Join-Path $SessionDir "recording"
    $recordingLog = Join-Path $SessionDir "session_recorder.log"
    $recordingArgs = @(
        "scripts\session_recorder.py",
        "--event-log", $EventLog,
        "--limit", $SummaryLimit,
        "--session-id", $SessionId,
        "--output-dir", $recordingDir
    )
    & python @recordingArgs *> $recordingLog
    if ($LASTEXITCODE -ne 0) {
        throw "session_recorder.py failed. See $recordingLog"
    }
}

function Invoke-SessionQualityGate {
    $recordingDir = Join-Path $SessionDir "recording"
    $qualityLog = Join-Path $SessionDir "session_quality_gate.log"
    $qualityArgs = @(
        "scripts\inspect_session_recording.py",
        $recordingDir
    )
    & python @qualityArgs *> $qualityLog
    $qualityExitCode = $LASTEXITCODE
    $qualityReport = Join-Path $recordingDir "session_quality_report.json"
    if (Test-Path -LiteralPath $qualityReport) {
        $payload = Get-Content -LiteralPath $qualityReport -Raw -Encoding UTF8 | ConvertFrom-Json
        $summary = $payload.summary
        $qualityStatus = if ($payload.passed) { "PASS" } else { "FAIL" }
        Write-SessionLine ("Quality gate: {0} score={1} errors={2} warnings={3}" -f `
            $qualityStatus,
            $payload.quality_score,
            $summary.errors,
            $summary.warnings)
    } else {
        Write-SessionLine "Quality gate report was not written. See $qualityLog"
    }
    if ($qualityExitCode -ne 0) {
        Write-SessionLine "Quality gate returned exit code $qualityExitCode; session continues for inspection."
    }
}

New-Item -ItemType Directory -Path $SessionDir -Force | Out-Null
Set-Location $RepoRoot

if (-not $BrokerIp) {
    $BrokerIp = Get-PreferredBrokerIp
}

Write-SessionLine "Ego Link supervised local session: $SessionId"
Write-SessionLine "Repository: $RepoRoot"
Write-SessionLine "Session directory: $SessionDir"

$brokerPid = 0
if ($NoBroker) {
    Write-SessionLine "Broker startup skipped by -NoBroker."
} else {
    $brokerLog = Join-Path $SessionDir "mosquitto_start.log"
    Write-SessionLine "Ensuring Mosquitto LAN broker at $BrokerIp`:$BrokerPort."
    $brokerArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", "scripts\start_mosquitto_lan.ps1",
        "-BrokerIp", $BrokerIp,
        "-Port", $BrokerPort
    )
    if ($RestartBroker) {
        $brokerArgs += "-Restart"
    }
    & powershell @brokerArgs *> $brokerLog
    $brokerPid = Get-ListenerPid -LocalAddress $BrokerIp -Port $BrokerPort
    Write-SessionLine "Broker PID: $brokerPid"
}

$dashboardPid = 0
if ($NoDashboard) {
    Write-SessionLine "Dashboard startup skipped by -NoDashboard."
} else {
    $dashboardPid = Get-ListenerPid -LocalAddress $DashboardHost -Port $DashboardPort
    if ($RestartDashboard -and $dashboardPid) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $dashboardPid"
        if ($proc.CommandLine -like "*pc_simulator\app.py*") {
            Write-SessionLine "Stopping existing Dashboard PID $dashboardPid."
            Stop-Process -Id $dashboardPid -Force
            Start-Sleep -Milliseconds 700
            $dashboardPid = 0
        }
    }
    if (-not $dashboardPid) {
        $dashboardOut = Join-Path $SessionDir "dashboard.stdout.log"
        $dashboardErr = Join-Path $SessionDir "dashboard.stderr.log"
        Write-SessionLine "Starting Dashboard at http://$DashboardHost`:$DashboardPort."
        $dashboardProc = Start-Process -FilePath python `
            -ArgumentList @("pc_simulator\app.py", "--host", $DashboardHost, "--port", $DashboardPort) `
            -WorkingDirectory $RepoRoot `
            -RedirectStandardOutput $dashboardOut `
            -RedirectStandardError $dashboardErr `
            -WindowStyle Hidden `
            -PassThru
        Start-Sleep -Seconds 2
        $dashboardPid = $dashboardProc.Id
    } else {
        Write-SessionLine "Dashboard already listening at http://$DashboardHost`:$DashboardPort."
    }
    Write-SessionLine "Dashboard PID: $dashboardPid"
}

$workerPid = 0
if ($NoWorker) {
    Write-SessionLine "MQTT Safety worker startup skipped by -NoWorker."
} else {
    $workerOut = Join-Path $SessionDir "mqtt_safety_worker.stdout.log"
    $workerErr = Join-Path $SessionDir "mqtt_safety_worker.stderr.log"
    $workerArgs = @(
        "pc_simulator\mqtt_worker.py",
        "--host", $BrokerIp,
        "--port", $BrokerPort,
        "--process-safety",
        "--safety-process-limit", $SafetyProcessLimit
    )
    if ($MaxMessages -gt 0) {
        $workerArgs += @("--max-messages", $MaxMessages)
    }
    if ($WaitSeconds -gt 0) {
        $workerArgs += @("--wait-seconds", $WaitSeconds)
    }
    Write-SessionLine "Starting live MQTT Safety worker."
    $workerProc = Start-Process -FilePath python `
        -ArgumentList $workerArgs `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $workerOut `
        -RedirectStandardError $workerErr `
        -WindowStyle Hidden `
        -PassThru
    $workerPid = $workerProc.Id
    Write-SessionLine "MQTT Safety worker PID: $workerPid"
}

Write-SessionSummary -DashboardPid $dashboardPid -WorkerPid $workerPid

if ($NoRecorder) {
    Write-SessionLine "Session recorder skipped by -NoRecorder."
} else {
    Write-SessionLine "Writing M1 session recording."
    Write-SessionRecording
    if ($NoQualityGate) {
        Write-SessionLine "Session quality gate skipped by -NoQualityGate."
    } else {
        Write-SessionLine "Running M1 session quality gate."
        Invoke-SessionQualityGate
    }
}

Write-SessionLine "Dashboard URL: http://$DashboardHost`:$DashboardPort"
Write-SessionLine "Session summary: $(Join-Path $SessionDir 'session_summary.md')"
Write-SessionLine "Session JSON: $(Join-Path $SessionDir 'session_summary.json')"
Write-SessionLine "Session recording: $(Join-Path $SessionDir 'recording\session_recording.md')"
Write-SessionLine "Session quality: $(Join-Path $SessionDir 'recording\session_quality_report.md')"
Write-SessionLine "Session log: $(Join-Path $SessionDir 'session.log')"

if ($Watch) {
    Write-SessionLine "Watch mode enabled. Press Ctrl+C to stop watching; background processes will keep running."
    while ($true) {
        Write-SessionSummary -DashboardPid $dashboardPid -WorkerPid $workerPid
        Clear-Host
        Get-Content -LiteralPath (Join-Path $SessionDir "session_summary.md") -Raw
        Start-Sleep -Seconds $WatchIntervalSeconds
    }
}
