param(
    [string]$LogDirectory = "$env:ProgramData\NewLight_Analysis\logs"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-SetupLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    Write-Host $line
    Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
}

function Stop-WithCode {
    param([int]$Code, [string]$Message)
    Write-SetupLog $Message
    exit $Code
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$adminRole = [Security.Principal.WindowsBuiltInRole]::Administrator
if (-not $principal.IsInRole($adminRole)) {
    Write-Error "Administrator privileges are required to install a display driver."
    exit 10
}

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$script:LogPath = Join-Path $LogDirectory "nvidia_driver_setup.log"
Write-SetupLog "Starting NVIDIA display-driver matching through Windows Update Agent."

try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = "NewLight_Analysis First Run Setup"
    $searcher = $session.CreateUpdateSearcher()
    $searchResult = $searcher.Search("IsInstalled=0 and Type='Driver'")

    $selected = New-Object -ComObject Microsoft.Update.UpdateColl
    for ($index = 0; $index -lt $searchResult.Updates.Count; $index++) {
        $update = $searchResult.Updates.Item($index)
        $title = [string]$update.Title
        $driverClass = ""
        try { $driverClass = [string]$update.DriverClass } catch { }
        $isNvidia = $title -match "NVIDIA"
        $isDisplay = ($driverClass -eq "DISPLAY") -or ($title -match "display|graphics")
        if ($isNvidia -and $isDisplay) {
            if (-not $update.EulaAccepted) {
                $update.AcceptEula()
            }
            [void]$selected.Add($update)
            Write-SetupLog "Selected applicable update: $title (DriverClass=$driverClass)"
        }
    }

    if ($selected.Count -eq 0) {
        Stop-WithCode 20 "Windows Update returned no applicable NVIDIA display-driver update."
    }

    $downloader = $session.CreateUpdateDownloader()
    $downloader.Updates = $selected
    $downloadResult = $downloader.Download()
    Write-SetupLog "Download result code: $($downloadResult.ResultCode)"
    if ($downloadResult.ResultCode -ne 2) {
        Stop-WithCode 21 "NVIDIA display-driver download did not complete successfully."
    }

    $installer = $session.CreateUpdateInstaller()
    $installer.Updates = $selected
    $installResult = $installer.Install()
    Write-SetupLog "Install result code: $($installResult.ResultCode); reboot required: $($installResult.RebootRequired)"
    if ($installResult.ResultCode -ne 2) {
        Stop-WithCode 22 "NVIDIA display-driver installation did not complete successfully."
    }

    Write-SetupLog "NVIDIA display-driver installation completed successfully."
    exit 0
}
catch {
    Stop-WithCode 30 ("Windows Update driver installation failed: " + $_.Exception.Message)
}

