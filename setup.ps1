[CmdletBinding()]
param(
    [string]$PythonExe = "",
    [string]$PnpmExe = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

Push-Location -LiteralPath $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $ProjectPython)) {
        $PythonArguments = @()
        if (-not $PythonExe) {
            $PythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
            if ($PythonCommand) {
                $PythonExe = $PythonCommand.Source
                $PythonArguments = @("-3")
            } else {
                $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
                if (-not $PythonCommand) {
                    throw "Install Python 3.10+ or pass -PythonExe with its full path."
                }
                $PythonExe = $PythonCommand.Source
            }
        }
        Invoke-Checked $PythonExe ($PythonArguments + @("-c", "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ is required'"))
        Invoke-Checked $PythonExe ($PythonArguments + @("-m", "venv", ".venv"))
    }

    if (-not $PnpmExe) {
        $PnpmCommand = Get-Command pnpm.cmd, pnpm.exe, pnpm -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $PnpmCommand) {
            throw "Install Node.js and pnpm, or pass -PnpmExe with its full path. See README.md."
        }
        $PnpmExe = $PnpmCommand.Source
    }

    Invoke-Checked $ProjectPython @("-m", "pip", "install", "-r", "backend/requirements.txt")
    Push-Location -LiteralPath (Join-Path $ProjectRoot "frontend")
    try {
        if (Test-Path -LiteralPath "pnpm-lock.yaml") {
            Invoke-Checked $PnpmExe @("install", "--frozen-lockfile")
        } else {
            Invoke-Checked $PnpmExe @("install")
        }
    } finally {
        Pop-Location
    }

    Invoke-Checked $ProjectPython @("scripts/prepare_assets.py")
    Push-Location -LiteralPath (Join-Path $ProjectRoot "frontend")
    try {
        Invoke-Checked $PnpmExe @("run", "build")
    } finally {
        Pop-Location
    }
    Write-Host ""
    Write-Host "Repwise is ready. Run .\start.ps1, then open http://127.0.0.1:8765"
} finally {
    Pop-Location
}
