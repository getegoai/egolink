$port = New-Object System.IO.Ports.SerialPort "COM8", 115200
$port.ReadTimeout = 1000
try {
    $port.Open()
    Write-Host "Connected to COM8. Reading logs for 10s..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.ElapsedMilliseconds -lt 10000) {
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
