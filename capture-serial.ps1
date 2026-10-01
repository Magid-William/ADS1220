<#
.SYNOPSIS
    Capture the nice!nano USB CDC-ACM console (logs + Zephyr shell) to a file.

.DESCRIPTION
    EXP02 helper. Opens the CDC-ACM COM port the zmk-usb-logging snippet
    exposes, writes everything the device prints to -OutFile, and (optionally)
    types shell commands at fixed intervals after a settle.

    With -Reset it sends `kernel reboot cold` after a delay and then reconnects
    across the USB re-enumeration, so the boot log is captured into the same
    file.

    The baud rate is ignored by CDC-ACM; it is only used to open the port.

.EXAMPLE
    .\capture-serial.ps1 -ComPort COM8 -OutFile exp02-boot.log -Seconds 20 -Reset

.EXAMPLE
    .\capture-serial.ps1 -ComPort COM8 -OutFile exp02-cmds.log -Seconds 22 `
        -Commands 'tpoint status','tpoint calib','tpoint sample 8'
#>
param(
    [string]$ComPort = "COM8",
    [int]$BaudRate = 115200,
    [Parameter(Mandatory=$true)]
    [string]$OutFile,
    [int]$Seconds = 20,
    [string[]]$Commands = @(),
    [int]$SettleSeconds = 3,
    [int]$CommandIntervalSeconds = 2,
    [switch]$Reset,
    [int]$ResetAfterSeconds = 3
)

$ErrorActionPreference = "Stop"

function Open-CdcPort {
    param([string]$Name, [int]$Rate)
    $p = New-Object System.IO.Ports.SerialPort $Name,$Rate,None,8,1
    $p.ReadTimeout = 200
    $p.WriteTimeout = 1000
    $p.DtrEnable = $true
    $p.RtsEnable = $true
    $p.Open()
    return $p
}

Write-Host "=== EXP02 serial capture ($ComPort -> $OutFile) ==="

try {
    $port = Open-CdcPort -Name $ComPort -Rate $BaudRate
} catch {
    Write-Host "ERROR: cannot open ${ComPort}: $($_.Exception.Message)"
    exit 1
}

$writer = New-Object System.IO.StreamWriter($OutFile, $false)
$writer.WriteLine("# EXP02 capture  port=$ComPort  start=$(Get-Date -Format o)")

$deadline = (Get-Date).AddSeconds($Seconds)
$cmdIndex = 0
$nextCmdAt = (Get-Date).AddSeconds($SettleSeconds)
$resetSent = $false
$resetAt = (Get-Date).AddSeconds($ResetAfterSeconds)

while ((Get-Date) -lt $deadline) {
    try {
        $chunk = $port.ReadExisting()
        if ($chunk.Length -gt 0) {
            $writer.Write($chunk)
            $writer.Flush()
            Write-Host -NoNewline $chunk
        }
    } catch {
        # Port dropped (likely a reboot / USB re-enumeration). Reconnect and keep going.
        $writer.WriteLine()
        $writer.WriteLine("### port error, reconnecting: $($_.Exception.Message)")
        $writer.Flush()
        try { $port.Close() } catch {}
        $port = $null
        for ($i = 0; $i -lt 20 -and -not $port; $i++) {
            Start-Sleep -Milliseconds 700
            try { $port = Open-CdcPort -Name $ComPort -Rate $BaudRate } catch { $port = $null }
        }
        if ($port) {
            $writer.WriteLine("### reconnected $(Get-Date -Format o)")
            $writer.Flush()
            Write-Host "`n### reconnected"
        } else {
            $writer.WriteLine("### reconnect FAILED")
            $writer.Flush()
            Write-Host "`n### reconnect FAILED"
            break
        }
        continue
    }

    if ($Reset -and -not $resetSent -and (Get-Date) -ge $resetAt) {
        $writer.WriteLine()
        $writer.WriteLine("### sent: kernel reboot cold")
        $writer.Flush()
        Write-Host "`n>>> kernel reboot cold"
        try { $port.WriteLine("kernel reboot cold") } catch {}
        $resetSent = $true
    }

    if ($cmdIndex -lt $Commands.Count -and (Get-Date) -ge $nextCmdAt) {
        $cmd = $Commands[$cmdIndex]
        $writer.WriteLine()
        $writer.WriteLine("### sent: $cmd")
        $writer.Flush()
        Write-Host "`n>>> $cmd"
        try { $port.WriteLine($cmd) } catch {}
        $cmdIndex++
        $nextCmdAt = (Get-Date).AddSeconds($CommandIntervalSeconds)
    }

    Start-Sleep -Milliseconds 50
}

$writer.WriteLine()
$writer.WriteLine("# end=$(Get-Date -Format o)")
$writer.Close()
if ($port) { try { $port.Close() } catch {} }

Write-Host "`n=== done: $OutFile ==="
