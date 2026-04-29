param(
    [switch]$AllowStandaloneOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $ProjectRoot ".venv-win-build"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$SpecFile = Join-Path $PSScriptRoot "HRResumeRegistryAssistant.spec"
$InstallerScript = Join-Path $PSScriptRoot "installer.iss"
$ExePath = Join-Path $ProjectRoot "dist\HRResumeRegistryAssistant.exe"
$InstallerPath = Join-Path $ProjectRoot "dist\installer\HRResumeRegistryAssistantSetup.exe"

Write-Host "== HR Resume Registry Assistant: Windows build =="
Write-Host "Project: $ProjectRoot"

$PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue

if (-not $PythonLauncher -and -not $PythonCommand) {
    throw "Python не найден. Установите Python 3.11+ для Windows и повторите сборку."
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating build virtual environment..."
    if ($PythonLauncher) {
        & $PythonLauncher.Source -3 -m venv $VenvDir
    }
    else {
        & $PythonCommand.Source -m venv $VenvDir
    }
}

Write-Host "Installing build dependencies..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt") pyinstaller==6.11.1

Write-Host "Running tests..."
& $PythonExe -m pytest

Write-Host "Building standalone EXE..."
Push-Location $PSScriptRoot
try {
    & $PythonExe -m PyInstaller --clean --noconfirm `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build\pyinstaller") `
        $SpecFile
}
finally {
    Pop-Location
}

if (-not (Test-Path $ExePath)) {
    throw "EXE не найден после сборки: $ExePath"
}

$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }

if ($InnoCandidates.Count -eq 0) {
    if ($AllowStandaloneOnly) {
        Write-Warning "Inno Setup 6 не найден. Установите его: winget install JRSoftware.InnoSetup"
        Write-Host "Standalone EXE готов: $ExePath"
        exit 0
    }

    throw "Inno Setup 6 не найден, поэтому installer .exe не создан. Установите: winget install JRSoftware.InnoSetup. Для сборки только standalone EXE используйте: .\packaging\build_windows.ps1 -AllowStandaloneOnly"
}

Write-Host "Building installer..."
& $InnoCandidates[0] $InstallerScript

if (-not (Test-Path $InstallerPath)) {
    throw "Инсталлятор не найден после сборки: $InstallerPath"
}

Write-Host ""
Write-Host "DONE"
Write-Host "EXE:       $ExePath"
Write-Host "Installer: $InstallerPath"
