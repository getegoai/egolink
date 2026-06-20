param(
    [string]$BrokerIp = "",
    [int]$Port = 1883,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repo "pc_simulator\runtime"
$pidFile = Join-Path $runtime "mosquitto-lan.pid"
$confFile = Join-Path $runtime "mosquitto-lan.conf"
$logFile = Join-Path $runtime "mosquitto-lan.log"
$mosquitto = "C:\Program Files\mosquitto\mosquitto.exe"

if (-not (Test-Path -LiteralPath $mosquitto)) {
    throw "Mosquitto is not installed at $mosquitto"
}

if (-not $BrokerIp) {
    $candidate = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.AddressState -eq "Preferred" } |
        Sort-Object { if ($_.InterfaceAlias -eq "WLAN") { 0 } else { 1 } }, InterfaceAlias |
        Select-Object -First 1
    if (-not $candidate) {
        throw "No preferred non-loopback IPv4 address found."
    }
    $BrokerIp = $candidate.IPAddress
}

if ($Restart -and (Test-Path -LiteralPath $pidFile)) {
    $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ($oldPid) {
        Stop-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

@"
listener $Port $BrokerIp
allow_anonymous true
persistence false
log_dest file $logFile
log_type error
log_type warning
log_type notice
log_type information
connection_messages true
"@ | Set-Content -LiteralPath $confFile -Encoding ASCII

& $mosquitto -c $confFile --test-config | Out-Host

$existing = Get-NetTCPConnection -LocalAddress $BrokerIp -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Mosquitto LAN broker already listening at $BrokerIp`:$Port pid=$($existing.OwningProcess)"
    return
}

$proc = Start-Process -FilePath $mosquitto -ArgumentList @("-c", $confFile) -WindowStyle Hidden -PassThru
$proc.Id | Set-Content -LiteralPath $pidFile -Encoding ASCII
Start-Sleep -Seconds 1

$listener = Get-NetTCPConnection -LocalAddress $BrokerIp -LocalPort $Port -ErrorAction SilentlyContinue
if (-not $listener) {
    throw "Mosquitto LAN broker did not start at $BrokerIp`:$Port"
}

Write-Output "Mosquitto LAN broker listening at $BrokerIp`:$Port pid=$($proc.Id)"
