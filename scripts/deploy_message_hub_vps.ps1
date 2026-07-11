param(
    [string]$HostName = $env:EGOLINK_VPS_HOST,
    [string]$User = $(if ($env:EGOLINK_VPS_USER) { $env:EGOLINK_VPS_USER } else { "root" }),
    [string]$SshKey = $env:EGOLINK_SSH_KEY,
    [string]$RemoteDir = "/opt/egolink-message-hub",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8790,
    [switch]$Public,
    [switch]$IncludeFieldReportSummaries,
    [switch]$IncludeDataFlywheelSummaries,
    [switch]$IncludeTrainingExperimentSummaries,
    [switch]$IncludeTrainingRunSummaries,
    [switch]$IncludeTrainingFeatureSummaries,
    [switch]$IncludeTrainingRunnerDryRunSummaries,
    [switch]$IncludeTrainingBaselineEvalSummaries,
    [switch]$IncludeTrainingHandoffSummaries,
    [switch]$IncludeTrainingJobSummaries,
    [switch]$IncludeSyntheticTrainingChainSummaries,
    [switch]$IncludeD1TrainingReadinessSummaries,
    [switch]$IncludeD1LabelingIntakeSummaries,
    [switch]$IncludeD1LabelingQueueSummaries,
    [switch]$IncludeD1LabelingReviewSummaries,
    [switch]$IncludeD1LabelingDecisionSummaries,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

if (-not $HostName) {
    throw "HostName is required. Pass -HostName or set EGOLINK_VPS_HOST."
}

if ($Public -and $ListenHost -eq "127.0.0.1") {
    $ListenHost = "0.0.0.0"
}

if ($ListenHost -eq "0.0.0.0" -and -not $env:EGOLINK_MESSAGE_HUB_TOKEN) {
    throw "Public listen requires EGOLINK_MESSAGE_HUB_TOKEN in the local environment. Do not commit this token."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$packageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("egolink-message-hub-package-" + [System.Guid]::NewGuid().ToString("N"))
$archive = Join-Path ([System.IO.Path]::GetTempPath()) ("egolink-message-hub-" + [System.Guid]::NewGuid().ToString("N") + ".tar.gz")

function Copy-RelativePath {
    param([string]$RelativePath)
    $source = Join-Path $repoRoot $RelativePath
    $target = Join-Path $packageRoot $RelativePath
    if (Test-Path $source -PathType Container) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -Recurse -Force -Path (Join-Path $source "*") -Destination $target
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -Path $source -Destination $target
    }
}

function Copy-ServerSource {
    $target = Join-Path $packageRoot "server"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Force -Path (Join-Path $repoRoot "server\*.py") -Destination $target
    Copy-Item -Force -Path (Join-Path $repoRoot "server\.env.example") -Destination $target
}

function Copy-FieldReportSummaries {
    $allowedNames = @(
        "d1_web_api_report.json",
        "d1_web_api_report.md",
        "d1_field_companion_summary.json",
        "d1_field_companion_summary.md",
        "d1_field_observation_report.json",
        "d1_field_observation_report.md",
        "d1_field_observation_status.json",
        "power_curve_report.json",
        "power_curve_report.md",
        "d1_demo_report.json",
        "d1_demo_report.md",
        "d1_postrun_collection_summary.json",
        "d1_postrun_collection_summary.md",
        "location_accuracy_report.json",
        "location_accuracy_report.md"
    )
    $reportFiles = @()
    foreach ($dir in @("reports\d1_web_api", "reports\d1_field_companion", "reports\d1_field_observation", "reports\power", "reports\d1_demo", "reports\d1_postrun", "reports\location_accuracy")) {
        $sourceDir = Join-Path $repoRoot $dir
        if (Test-Path $sourceDir -PathType Container) {
            $reportFiles += Get-ChildItem -Path $sourceDir -Recurse -File |
                Where-Object { $allowedNames -contains $_.Name }
        }
    }

    $amoledDir = Join-Path $repoRoot "reports\amoled_visible_status"
    if (Test-Path $amoledDir -PathType Container) {
        $reportFiles += Get-ChildItem -Path $amoledDir -Recurse -File |
            Where-Object { $_.Name -like "*.summary.json" }
    }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy report outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-DataFlywheelSummaries {
    $dataFlywheelDir = Join-Path $repoRoot "reports\data_flywheel"
    if (-not (Test-Path $dataFlywheelDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "data_flywheel_status.json",
        "data_flywheel_status.md"
    )
    $reportFiles = Get-ChildItem -Path $dataFlywheelDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy data flywheel summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingExperimentSummaries {
    $trainingExperimentDir = Join-Path $repoRoot "reports\training_experiments"
    if (-not (Test-Path $trainingExperimentDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_experiment_plan.json",
        "training_experiment_plan.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingExperimentDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training experiment summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingRunSummaries {
    $trainingRunDir = Join-Path $repoRoot "reports\training_runs"
    if (-not (Test-Path $trainingRunDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_run_preflight.json",
        "training_run_preflight.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingRunDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training run summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingFeatureSummaries {
    $trainingFeatureDir = Join-Path $repoRoot "reports\training_features"
    if (-not (Test-Path $trainingFeatureDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_feature_manifest.json",
        "training_feature_manifest.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingFeatureDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training feature summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingRunnerDryRunSummaries {
    $trainingRunnerDryRunDir = Join-Path $repoRoot "reports\training_runner_dry_runs"
    if (-not (Test-Path $trainingRunnerDryRunDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_runner_dry_run.json",
        "training_runner_dry_run.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingRunnerDryRunDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training runner dry-run summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingBaselineEvalSummaries {
    $trainingBaselineEvalDir = Join-Path $repoRoot "reports\training_baseline_evals"
    if (-not (Test-Path $trainingBaselineEvalDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_baseline_eval.json",
        "training_baseline_eval.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingBaselineEvalDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training baseline eval summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingHandoffSummaries {
    $trainingHandoffDir = Join-Path $repoRoot "reports\training_handoffs"
    if (-not (Test-Path $trainingHandoffDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_handoff_bundle.json",
        "training_handoff_bundle.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingHandoffDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training handoff summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-TrainingJobSummaries {
    $trainingJobDir = Join-Path $repoRoot "reports\training_jobs"
    if (-not (Test-Path $trainingJobDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "training_job_plan.json",
        "training_job_plan.md"
    )
    $reportFiles = Get-ChildItem -Path $trainingJobDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy training job summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-SyntheticTrainingChainSummaries {
    $syntheticTrainingChainDir = Join-Path $repoRoot "reports\synthetic_training_chain"
    if (-not (Test-Path $syntheticTrainingChainDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "synthetic_training_chain.json",
        "synthetic_training_chain.md"
    )
    $reportFiles = Get-ChildItem -Path $syntheticTrainingChainDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy synthetic training chain summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-D1TrainingReadinessSummaries {
    $d1TrainingReadinessDir = Join-Path $repoRoot "reports\d1_training_readiness"
    if (-not (Test-Path $d1TrainingReadinessDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "d1_training_readiness.json",
        "d1_training_readiness.md"
    )
    $reportFiles = Get-ChildItem -Path $d1TrainingReadinessDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy D1 training readiness summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-D1LabelingIntakeSummaries {
    $d1LabelingIntakeDir = Join-Path $repoRoot "reports\d1_labeling_intake"
    if (-not (Test-Path $d1LabelingIntakeDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "d1_labeling_intake.json",
        "d1_labeling_intake.md"
    )
    $reportFiles = Get-ChildItem -Path $d1LabelingIntakeDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy D1 labeling intake summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-D1LabelingQueueSummaries {
    $d1LabelingQueueDir = Join-Path $repoRoot "reports\d1_labeling_queue"
    if (-not (Test-Path $d1LabelingQueueDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "d1_labeling_queue.json",
        "d1_labeling_queue.md"
    )
    $reportFiles = Get-ChildItem -Path $d1LabelingQueueDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy D1 labeling queue summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-D1LabelingReviewSummaries {
    $d1LabelingReviewDir = Join-Path $repoRoot "reports\d1_labeling_reviews"
    if (-not (Test-Path $d1LabelingReviewDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "d1_labeling_review_packet.json",
        "d1_labeling_review_packet.md"
    )
    $reportFiles = Get-ChildItem -Path $d1LabelingReviewDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy D1 labeling review summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function Copy-D1LabelingDecisionSummaries {
    $d1LabelingDecisionDir = Join-Path $repoRoot "reports\d1_labeling_decisions"
    if (-not (Test-Path $d1LabelingDecisionDir -PathType Container)) {
        return
    }
    $allowedNames = @(
        "d1_labeling_decision_template.json",
        "d1_labeling_decision_template.md"
    )
    $reportFiles = Get-ChildItem -Path $d1LabelingDecisionDir -Recurse -File |
        Where-Object { $allowedNames -contains $_.Name }

    $repoFull = (Resolve-Path $repoRoot).Path.TrimEnd("\", "/")
    foreach ($file in $reportFiles) {
        $fileFull = $file.FullName
        if (-not $fileFull.StartsWith($repoFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to copy D1 labeling decision summary outside repository: $fileFull"
        }
        $relative = $fileFull.Substring($repoFull.Length).TrimStart("\", "/")
        $target = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -Force -LiteralPath $file.FullName -Destination $target
    }
}

function SshArgs {
    $args = @()
    if ($SshKey) {
        $args += @("-i", $SshKey)
    }
    $args += @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "$User@$HostName")
    return $args
}

function ScpArgs {
    param([string]$LocalPath, [string]$RemotePath)
    $args = @()
    if ($SshKey) {
        $args += @("-i", $SshKey)
    }
    $args += @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", $LocalPath, "$User@$HostName`:$RemotePath")
    return $args
}

function ShellQuote {
    param([string]$Value)
    return "'" + ($Value -replace "'", "'`"`"'") + "'"
}

try {
    New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
    Copy-ServerSource
    Copy-RelativePath "docs\current\key_releases"
    Copy-RelativePath "docs\generated\progress_board.json"
    Copy-RelativePath "pc_simulator\__init__.py"
    Copy-RelativePath "pc_simulator\protocol.py"
    Copy-RelativePath "scripts\run_message_hub.py"
    Copy-RelativePath "shared\contracts"
    Copy-RelativePath "README.md"
    if ($IncludeFieldReportSummaries) {
        Copy-FieldReportSummaries
    }
    if ($IncludeDataFlywheelSummaries) {
        Copy-DataFlywheelSummaries
    }
    if ($IncludeTrainingExperimentSummaries) {
        Copy-TrainingExperimentSummaries
    }
    if ($IncludeTrainingRunSummaries) {
        Copy-TrainingRunSummaries
    }
    if ($IncludeTrainingFeatureSummaries) {
        Copy-TrainingFeatureSummaries
    }
    if ($IncludeTrainingRunnerDryRunSummaries) {
        Copy-TrainingRunnerDryRunSummaries
    }
    if ($IncludeTrainingBaselineEvalSummaries) {
        Copy-TrainingBaselineEvalSummaries
    }
    if ($IncludeTrainingHandoffSummaries) {
        Copy-TrainingHandoffSummaries
    }
    if ($IncludeTrainingJobSummaries) {
        Copy-TrainingJobSummaries
    }
    if ($IncludeSyntheticTrainingChainSummaries) {
        Copy-SyntheticTrainingChainSummaries
    }
    if ($IncludeD1TrainingReadinessSummaries) {
        Copy-D1TrainingReadinessSummaries
    }
    if ($IncludeD1LabelingIntakeSummaries) {
        Copy-D1LabelingIntakeSummaries
    }
    if ($IncludeD1LabelingQueueSummaries) {
        Copy-D1LabelingQueueSummaries
    }
    if ($IncludeD1LabelingReviewSummaries) {
        Copy-D1LabelingReviewSummaries
    }
    if ($IncludeD1LabelingDecisionSummaries) {
        Copy-D1LabelingDecisionSummaries
    }

    Push-Location $packageRoot
    try {
        tar -czf $archive .
    } finally {
        Pop-Location
    }

    $remoteArchive = "/tmp/egolink-message-hub.tar.gz"
    & scp @((ScpArgs $archive $remoteArchive))
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed with exit code $LASTEXITCODE"
    }

    $startCommand = if ($NoStart) { "true" } else { "systemctl daemon-reload && systemctl enable egolink-message-hub.service && systemctl restart egolink-message-hub.service" }
    $envCommand = @"
if [ ! -f /etc/egolink-message-hub.env ]; then
  install -m 600 /dev/null /etc/egolink-message-hub.env
fi
"@
    if ($env:EGOLINK_MESSAGE_HUB_TOKEN) {
        $envLine = "EGOLINK_MESSAGE_HUB_TOKEN=$($env:EGOLINK_MESSAGE_HUB_TOKEN)"
        $envCommand = "printf '%s\n' $(ShellQuote $envLine) >/etc/egolink-message-hub.env`nchmod 600 /etc/egolink-message-hub.env"
    }
    $remoteScript = @"
set -eu
mkdir -p '$RemoteDir'
tar -xzf '$remoteArchive' -C '$RemoteDir'
rm -rf '$RemoteDir/server/runtime' '$RemoteDir/server/__pycache__'
mkdir -p /var/lib/egolink-message-hub
$envCommand
cat >/etc/systemd/system/egolink-message-hub.service <<'EOF'
[Unit]
Description=Ego Link P0 Message Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$RemoteDir
EnvironmentFile=-/etc/egolink-message-hub.env
ExecStart=/usr/bin/python3 $RemoteDir/scripts/run_message_hub.py --host $ListenHost --port $Port --db /var/lib/egolink-message-hub/message_hub.db
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
$startCommand
systemctl --no-pager --full status egolink-message-hub.service || true
"@

    # Windows here-strings use CRLF; remote bash must receive LF-only input.
    $remoteScript = $remoteScript.Replace("`r", "")
    $remoteScript | ssh @((SshArgs)) "bash -s"
    if ($LASTEXITCODE -ne 0) {
        throw "remote install failed with exit code $LASTEXITCODE"
    }

    Write-Host "Deployed Ego Link Message Hub to ${User}@${HostName}:${RemoteDir}"
    Write-Host "Service: egolink-message-hub.service"
    Write-Host "Listen: $ListenHost`:$Port"
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $packageRoot
    Remove-Item -Force -ErrorAction SilentlyContinue $archive
}
