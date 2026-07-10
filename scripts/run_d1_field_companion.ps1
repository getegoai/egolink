param(
    [string]$HubUrl = "http://127.0.0.1:8790",
    [string]$TokenFile = "",
    [string]$RunId = ("d1-field-companion-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$DeviceId = "",
    [double]$DurationMinutes = 240,
    [double]$PollIntervalSec = 60,
    [int]$SampleCount = 0,
    [double]$MaxStaleSec = 180,
    [int]$TimeoutSec = 10,
    [string]$AmoledPort = "",
    [int]$AmoledReadWindowSeconds = 8,
    [string]$OutputRoot = "",
    [switch]$NoAmoled,
    [switch]$NoObserver,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $TokenFile) {
    $TokenFile = Join-Path $RepoRoot "server\runtime\vps_message_hub_token.txt"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "reports\d1_field_companion"
}

function Show-Help {
    @"
Start the D1 field observer and AMOLED status sidecar with one shared run ID.

Examples:
  powershell -ExecutionPolicy Bypass -File scripts\run_d1_field_companion.ps1 -HubUrl http://203.0.113.10:8790 -DurationMinutes 240 -PollIntervalSec 60
  powershell -ExecutionPolicy Bypass -File scripts\run_d1_field_companion.ps1 -HubUrl http://203.0.113.10:8790 -AmoledPort COM9 -SampleCount 2 -PollIntervalSec 10
  powershell -ExecutionPolicy Bypass -File scripts\run_d1_field_companion.ps1 -NoAmoled -SampleCount 1

The companion runner launches finite child processes, waits for them, and writes
one JSON/Markdown summary. It reads Message Hub state, writes AMOLED sidecar
serial when enabled, and does not send Message Hub or 4G-board commands.
"@
}

if ($Help) {
    Show-Help
    return
}

if ($NoAmoled -and $NoObserver) {
    throw "At least one child runner must be enabled."
}
if ($DurationMinutes -le 0) {
    throw "DurationMinutes must be positive."
}
if ($PollIntervalSec -lt 0) {
    throw "PollIntervalSec must be >= 0."
}
if ($MaxStaleSec -le 0) {
    throw "MaxStaleSec must be positive."
}
if ($TimeoutSec -lt 1) {
    throw "TimeoutSec must be >= 1."
}
if ($AmoledReadWindowSeconds -lt 1) {
    throw "AmoledReadWindowSeconds must be >= 1."
}

function Resolve-SampleCount {
    if ($SampleCount -gt 0) {
        return $SampleCount
    }
    $denominator = [Math]::Max([double]$PollIntervalSec, 1.0)
    return [Math]::Max(1, [int][Math]::Floor(($DurationMinutes * 60.0) / $denominator) + 1)
}

function Quote-Arg {
    param([string]$Value)
    if ($null -eq $Value) {
        return '""'
    }
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Join-CommandLine {
    param([string[]]$ArgumentValues)
    return ($ArgumentValues | ForEach-Object { Quote-Arg $_ }) -join " "
}

function Start-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$StdoutPath,
        [string]$StderrPath
    )
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList (Join-CommandLine $Arguments) `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Hidden `
        -PassThru
    return [ordered]@{
        name = $Name
        process = $process
        file = $FilePath
        argv = @($FilePath) + $Arguments
        stdout = $StdoutPath
        stderr = $StderrPath
    }
}

function Read-JsonFileObject {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
}

function Get-EffectiveChildExit {
    param(
        [string]$Name,
        [object]$RawExitCode,
        [object]$Summary
    )
    if ($null -ne $RawExitCode) {
        return [pscustomobject]@{
            code = [int]$RawExitCode
            source = "process_exit_code"
        }
    }
    if ($null -eq $Summary) {
        return [pscustomobject]@{
            code = 1
            source = "missing_summary"
        }
    }
    if ($Name -eq "d1_observer") {
        if ($Summary.result -eq "PASS" -or $Summary.result -eq "WARN") {
            return [pscustomobject]@{
                code = 0
                source = "observer_summary_result"
            }
        }
        return [pscustomobject]@{
            code = 1
            source = "observer_summary_result"
        }
    }
    if ($Name -eq "amoled_sidecar") {
        if ($Summary.ok -eq $true) {
            return [pscustomobject]@{
                code = 0
                source = "amoled_summary_ok"
            }
        }
        return [pscustomobject]@{
            code = 1
            source = "amoled_summary_ok"
        }
    }
    return [pscustomobject]@{
        code = 1
        source = "unknown_child_no_exit_code"
    }
}

function Write-Utf8NoBomText {
    param(
        [string]$Path,
        [string]$Content
    )
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Write-CompanionMarkdown {
    param(
        [string]$Path,
        [object]$Summary
    )
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# D1 Field Companion Summary")
    $lines.Add("")
    $lines.Add("- Result: $($Summary.result)")
    $lines.Add("- Run ID: $($Summary.run_id)")
    $lines.Add("- Hub: $($Summary.hub_url)")
    $lines.Add("- Sample count: $($Summary.sample_count)")
    $lines.Add("- Poll interval: $($Summary.poll_interval_sec) s")
    $lines.Add("")
    $lines.Add("## Children")
    $lines.Add("")
    foreach ($child in @($Summary.children)) {
        $lines.Add("- $($child.name): effective_exit=$($child.effective_exit_code), raw_exit=$($child.exit_code), enabled=$($child.enabled)")
        if ($child.summary_path) {
            $lines.Add("  - summary: $($child.summary_path)")
        }
        $lines.Add("  - stdout: $($child.stdout)")
        $lines.Add("  - stderr: $($child.stderr)")
    }
    $lines.Add("")
    $lines.Add("## Boundaries")
    $lines.Add("")
    $lines.Add("- Reads Message Hub Web/API state through the existing observer and sidecar tools.")
    $lines.Add("- Writes AMOLED serial only when the sidecar child is enabled.")
    $lines.Add("- Does not send Message Hub commands, contact the 4G-board serial port, flash firmware, modify GitLab, claim location accuracy, claim GNSS acceptance, or claim battery life.")
    Write-Utf8NoBomText -Path $Path -Content (($lines -join "`n") + "`n")
}

$resolvedSampleCount = Resolve-SampleCount
$companionDir = Join-Path $OutputRoot $RunId
$observerDir = Join-Path $companionDir "observer"
$amoledDir = Join-Path $companionDir "amoled"
New-Item -ItemType Directory -Path $companionDir -Force | Out-Null

$children = [System.Collections.Generic.List[object]]::new()

if (-not $NoObserver) {
    $observerArgs = @(
        (Join-Path $RepoRoot "scripts\observe_d1_field_run.py"),
        "--hub-url", $HubUrl,
        "--token-file", $TokenFile,
        "--output-dir", $observerDir,
        "--run-id", $RunId,
        "--duration-minutes", ([string]$DurationMinutes),
        "--poll-interval-sec", ([string]$PollIntervalSec),
        "--max-stale-sec", ([string]$MaxStaleSec),
        "--timeout", ([string]$TimeoutSec),
        "--sample-count", ([string]$resolvedSampleCount),
        "--json"
    )
    if ($DeviceId) {
        $observerArgs += @("--device-id", $DeviceId)
    }
    $children.Add((Start-LoggedProcess `
        -Name "d1_observer" `
        -FilePath "python" `
        -Arguments $observerArgs `
        -StdoutPath (Join-Path $companionDir "observer.stdout.log") `
        -StderrPath (Join-Path $companionDir "observer.stderr.log")))
}

if (-not $NoAmoled) {
    $amoledArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $RepoRoot "scripts\run_amoled_d1_status_sidecar.ps1"),
        "-HubUrl", $HubUrl,
        "-TokenFile", $TokenFile,
        "-SampleCount", ([string]$resolvedSampleCount),
        "-PollIntervalSec", ([string]$PollIntervalSec),
        "-ReadWindowSeconds", ([string]$AmoledReadWindowSeconds),
        "-SessionId", $RunId,
        "-OutputDir", $amoledDir
    )
    if ($DeviceId) {
        $amoledArgs += @("-DeviceId", $DeviceId)
    }
    if ($AmoledPort) {
        $amoledArgs += @("-Port", $AmoledPort)
    }
    $children.Add((Start-LoggedProcess `
        -Name "amoled_sidecar" `
        -FilePath "powershell.exe" `
        -Arguments $amoledArgs `
        -StdoutPath (Join-Path $companionDir "amoled.stdout.log") `
        -StderrPath (Join-Path $companionDir "amoled.stderr.log")))
}

foreach ($child in $children) {
    $child.process.WaitForExit()
    $child.process.Refresh()
}

$childSummaries = [System.Collections.Generic.List[object]]::new()
foreach ($child in $children) {
    $exitCode = $child.process.ExitCode
    $summaryPath = ""
    $summary = $null
    if ($child.name -eq "d1_observer") {
        $summaryPath = Join-Path $observerDir "d1_field_observation_report.json"
        $summary = Read-JsonFileObject -Path $summaryPath
    } elseif ($child.name -eq "amoled_sidecar") {
        $summaryPath = Join-Path $amoledDir "$RunId.summary.json"
        $summary = Read-JsonFileObject -Path $summaryPath
    }
    $exitInfo = Get-EffectiveChildExit -Name $child.name -RawExitCode $exitCode -Summary $summary
    $childSummaries.Add([ordered]@{
        name = $child.name
        enabled = $true
        exit_code = $exitCode
        effective_exit_code = $exitInfo.code
        exit_code_source = $exitInfo.source
        argv = $child.argv
        stdout = $child.stdout
        stderr = $child.stderr
        summary_path = $summaryPath
        summary = $summary
    })
}

if ($NoObserver) {
    $childSummaries.Add([ordered]@{
        name = "d1_observer"
        enabled = $false
        exit_code = $null
        effective_exit_code = $null
        exit_code_source = "disabled"
    })
}
if ($NoAmoled) {
    $childSummaries.Add([ordered]@{
        name = "amoled_sidecar"
        enabled = $false
        exit_code = $null
        effective_exit_code = $null
        exit_code_source = "disabled"
    })
}

$childFailures = @($childSummaries | Where-Object { $_.enabled -and $_.effective_exit_code -ne 0 })
$result = if ($childFailures.Count -gt 0) { "FAIL" } else { "PASS" }
$summaryJsonPath = Join-Path $companionDir "d1_field_companion_summary.json"
$summaryMarkdownPath = Join-Path $companionDir "d1_field_companion_summary.md"
$summary = [ordered]@{
    tool = "run_d1_field_companion"
    result = $result
    run_id = $RunId
    created_at = [DateTimeOffset]::UtcNow.ToString("o")
    hub_url = $HubUrl.TrimEnd("/")
    device_id = $DeviceId
    duration_minutes = $DurationMinutes
    sample_count = $resolvedSampleCount
    poll_interval_sec = $PollIntervalSec
    output_dir = $companionDir
    summary_path = $summaryJsonPath
    markdown_summary_path = $summaryMarkdownPath
    children = $childSummaries
    scope = [ordered]@{
        reads_message_hub_state = $true
        writes_amoled_serial = (-not $NoAmoled)
        sends_message_hub_commands = $false
        contacts_4g_board_serial = $false
        flashes_firmware = $false
        modifies_gitlab = $false
        claims_location_accuracy = $false
        claims_gnss_acceptance = $false
        claims_battery_life = $false
    }
}

$summaryJson = $summary | ConvertTo-Json -Depth 12
Write-Utf8NoBomText -Path $summaryJsonPath -Content $summaryJson
Write-CompanionMarkdown -Path $summaryMarkdownPath -Summary $summary
Write-Host $summaryJson

if ($result -eq "FAIL") {
    exit 2
}
