param(
    [switch]$UseCurrentPython,
    [switch]$IncludeSampleData
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv-build"
$DistRoot = Join-Path $ProjectRoot "dist"
$PortableDir = Join-Path $DistRoot "HRMatcherPortable"
$ExePath = Join-Path $PortableDir "HRMatcher.exe"

Write-Host "== HR Resume Matcher Portable: Windows build =="
Write-Host "Project: $ProjectRoot"

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw "Python не найден. Установите Python 3.11+ для Windows и повторите сборку."
}

$PythonExe = $PythonCommand.Source
if (-not $UseCurrentPython) {
    $VenvPythonExe = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $VenvPythonExe)) {
        Write-Host "Creating build virtual environment..."
        & $PythonExe -m venv $VenvDir
    }
    $PythonExe = $VenvPythonExe
}

Write-Host "Python: $PythonExe"
& $PythonExe --version

Write-Host "Installing dependencies..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements-dev.txt")

Write-Host "Running tests..."
$env:PYTHONPATH = $ProjectRoot
& $PythonExe -m pytest (Join-Path $ProjectRoot "tests") -q

if (Test-Path $PortableDir) {
    Remove-Item $PortableDir -Recurse -Force
}

Write-Host "Building portable EXE..."
& $PythonExe -m PyInstaller --clean --noconfirm --onefile --windowed `
    --name HRMatcher `
    --distpath $PortableDir `
    --workpath (Join-Path $ProjectRoot "build\pyinstaller") `
    --specpath (Join-Path $ProjectRoot "build") `
    (Join-Path $ProjectRoot "HRMatcher.py")

if (-not (Test-Path $ExePath)) {
    throw "EXE не найден после сборки: $ExePath"
}

New-Item -ItemType Directory -Force (Join-Path $PortableDir "config") | Out-Null
Copy-Item (Join-Path $ProjectRoot "config\name_aliases.json") (Join-Path $PortableDir "config\name_aliases.json") -Force
Copy-Item (Join-Path $ProjectRoot "README.md") (Join-Path $PortableDir "README.md") -Force
Copy-Item (Join-Path $ProjectRoot "WINDOWS_11_CHECKLIST_RU.md") (Join-Path $PortableDir "WINDOWS_11_CHECKLIST_RU.md") -Force

$SampleData = Join-Path $ProjectRoot "test_data\real_case"
if ($IncludeSampleData -and (Test-Path $SampleData)) {
    New-Item -ItemType Directory -Force (Join-Path $PortableDir "sample_data") | Out-Null
    Copy-Item $SampleData (Join-Path $PortableDir "sample_data\real_case") -Recurse -Force
}

Write-Host ""
Write-Host "DONE"
Write-Host "Portable folder: $PortableDir"
Write-Host "EXE: $ExePath"
