[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [switch]$OpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$FrontendEntry = Join-Path $ProjectRoot "frontend\dist\index.html"
if (-not (Test-Path -LiteralPath $ProjectPython)) {
    throw "Python environment is missing. Run .\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $FrontendEntry)) {
    throw "Frontend build is missing. Run .\setup.ps1 first."
}

Push-Location -LiteralPath $ProjectRoot
try {
    Write-Host "Repwise: http://127.0.0.1:$Port"
    Write-Host "Press Ctrl+C to stop. Workout records remain in the local data folder."
    if ($OpenBrowser) {
        Start-Process "http://127.0.0.1:$Port"
    }
    & $ProjectPython -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Repwise stopped with exit code $LASTEXITCODE. Check the error above."
    }
} finally {
    Pop-Location
}
