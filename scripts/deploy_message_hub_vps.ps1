param(
    [string]$HostName = $env:EGOLINK_VPS_HOST,
    [string]$User = $(if ($env:EGOLINK_VPS_USER) { $env:EGOLINK_VPS_USER } else { "root" }),
    [string]$SshKey = $env:EGOLINK_SSH_KEY,
    [string]$RemoteDir = "/opt/egolink-message-hub",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8790,
    [switch]$Public,
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
    Copy-RelativePath "pc_simulator\__init__.py"
    Copy-RelativePath "pc_simulator\protocol.py"
    Copy-RelativePath "scripts\run_message_hub.py"
    Copy-RelativePath "shared\contracts"
    Copy-RelativePath "README.md"

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
