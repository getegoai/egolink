$port = New-Object System.IO.Ports.SerialPort "COM8", 115200
$port.ReadTimeout = 1000
try {
    $port.Open()
    Write-Host "Resetting ESP32-S3 via RTS/DTR..."
    $port.DtrEnable = $false
    $port.RtsEnable = $true
    Start-Sleep -Milliseconds 100
    $port.RtsEnable = $false
    Start-Sleep -Milliseconds 100

    Write-Host "Reading boot log for 25s..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.ElapsedMilliseconds -lt 25000) {
        try {
            $line = $port.ReadLine()
            Write-Host $line
        } catch [System.TimeoutException] {}
    }
} finally {
    if ($port.IsOpen) {
        $port.Close()
    }
}
