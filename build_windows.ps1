$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv-build")) {
    python -m venv .venv-build
}

$python = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-build.txt
& $python smoke_test.py
& $python -m PyInstaller --noconfirm --clean --onefile --console --name EZ_Expedite desktop.py

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $PSScriptRoot "dist\EZ_Expedite.exe")
