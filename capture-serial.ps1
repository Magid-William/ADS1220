<#
.SYNOPSIS
    Capture the nice!nano USB CDC-ACM console (logs + Zephyr shell) to a file.

.DESCRIPTION
    EXP02 helper. Opens the CDC-ACM COM port the zmk-usb-logging snippet
    exposes, writes everything the device prints to -OutFile, and (optionally)
    types shell commands at 2 s intervals after a 3 s settle.

    The baud rate is ignored by CDC-ACM; 115200 is only used to open the port.

.EXAMPLE
    .\capture-serial.ps1 -ComPort COM22 -OutFile exp02-boot.log -Seconds 20 `
        -Commands 'tpoint status','tpoint sample 8','tpoint calib'
#>
param(
    [string]$ComPort = "COM8",
    [int]$BaudRate = 115200,
    [Parameter(Mandatory=$true)]
    [string]$OutFile,
    [int]$Seconds = 20,
    [string[]]$Commands = @(),
    [int]$SettleSeconds = 3,
    [int]$CommandIntervalSeconds = 2
)

$ErrorActionPreference = "Stop"

Write-Host "=== EXP02 serial capture ($ComPort -> $OutFile) ==="

$port = New-Object System.IO.Ports.SerialPort $ComPort, $BaudRate, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One
$port.ReadTimeout = 200
$port.WriteTimeout = 1000
$port.DtrEnable = $true
$port.RtsEnable = $true

try {
    $port.Open()
} catch {
    Write-Host "ERROR: cannot open ${ComPort}: $($_.Exception.Message)"
    exit 1
}

$writer = New-Object System.IO.StreamWriter($OutFile, $false)
$writer.WriteLine("# EXP02 capture  port=$ComPort  start=$(Get-Date -Format o)")

$deadline = (Get-Date).AddSeconds($Seconds)
$cmdIndex = 0
$nextCmdAt = (Get-Date).AddSeconds($SettleSeconds)

while ((Get-Date) -lt $deadline) {
    try {
        $chunk = $port.ReadExisting()
        if ($chunk.Length -gt 0) {
            $writer.Write($chunk)
            $writer.Flush()
            Write-Host -NoNewline $chunk
        }
    } catch {
        # read timeout - just keep polling
    }

    if ($cmdIndex -lt $Commands.Count -and (Get-Date) -ge $nextCmdAt) {
        $cmd = $Commands[$cmdIndex]
        $writer.WriteLine()
        $writer.WriteLine("### sent: $cmd")
        $writer.Flush()
        Write-Host "`n>>> $cmd"
        $port.WriteLine($cmd)
        $cmdIndex++
        $nextCmdAt = (Get-Date).AddSeconds($CommandIntervalSeconds)
    }

    Start-Sleep -Milliseconds 50
}

$writer.WriteLine()
$writer.WriteLine("# end=$(Get-Date -Format o)")
$writer.Close()
$port.Close()

Write-Host "`n=== done: $OutFile ==="
