$ErrorActionPreference = 'Stop'

Write-Host "=== Step 1: Activating Espressif Official Toolchain Profile ==="
. "C:\Espressif\tools\Microsoft.v5.4.2.PowerShell_profile.ps1"

$projectDir = "d:\pywork\egolink\firmware\hw021_pcb1_bringup"
$buildDir = "D:\tmp\pcb1_bringup_build"

Write-Host "=== Step 2: Building Firmware (hw021_pcb1_bringup) ==="
& idf.py -C $projectDir -B $buildDir build
if ($LASTEXITCODE -ne 0) {
    throw "idf.py build failed with exit code $LASTEXITCODE"
}

Write-Host "=== Step 3: Flashing to Hardware COM8 ==="
Push-Location $buildDir
try {
    & python -m esptool --chip esp32s3 -p COM8 -b 460800 --before default_reset --after hard_reset write_flash "@flash_args"
    if ($LASTEXITCODE -ne 0) {
        throw "esptool flash failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host "=== FLASHING COMPLETED SUCCESSFULLY! ==="
