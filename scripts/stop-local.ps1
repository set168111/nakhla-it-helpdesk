ï»¿$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$expectedPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Stop-VerifiedHelpdeskLauncher {
    param([string]$PidFile, [string]$ExpectedCommand)
    $pidPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $PidFile))
    if (-not $pidPath.StartsWith($projectRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'PID file is outside the IT HelpDesk workspace.'
    }
    if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
        Write-Output "No PID file: $PidFile"
        return
    }
    $launcherId = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$launcherId) -or $launcherId -le 0) {
        throw "Invalid launcher PID in $PidFile"
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $launcherId" -ErrorAction Stop
    if (-not $process) {
        Write-Output "Recorded launcher is no longer running: $PidFile"
        return
    }
    if ($process.ExecutablePath -ine $expectedPython -or
        -not $process.CommandLine -or
        $process.CommandLine.IndexOf($ExpectedCommand, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Process identity does not match $PidFile; nothing stopped."
    }
    & taskkill.exe /PID $launcherId /T /F
    if ($LASTEXITCODE -ne 0) { throw "Stopping verified launcher $launcherId failed." }
}

Stop-VerifiedHelpdeskLauncher 'evidence\ui-launch.pid' 'ui/app_ui.py'
Stop-VerifiedHelpdeskLauncher 'evidence\app-launch.pid' '-m uvicorn app.main:app'
Stop-VerifiedHelpdeskLauncher 'setup-api-launch.pid' '-m uvicorn services.helpdesk_api:app'
