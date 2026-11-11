# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Windows release of Nimcale (dist\Nimcale\Nimcale.exe and dist\Nimcale-<version>-windows-x64.zip).
# Requirements: Python 3.10-3.13 (64-bit) and 7-Zip (for the Mesa software renderer download).
# Usage (PowerShell, from the repository root):   .\scripts\build_windows.ps1
param([string]$Python = "python", [switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& $Python -m venv .venv-build
$py = ".\.venv-build\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt
if (-not $SkipTests) { & $py -m pytest -q; if ($LASTEXITCODE) { throw "tests failed" } }
& $py scripts\fetch_mesa.py; if ($LASTEXITCODE) { throw "Mesa download failed" }
& $py -m PyInstaller --noconfirm --clean nimcale.spec; if ($LASTEXITCODE) { throw "PyInstaller failed" }

$ver = (& $py -c "import nimcale; print(nimcale.__version__)").Trim()
$zip = "dist\Nimcale-$ver-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\Nimcale -DestinationPath $zip
Write-Host "OK -> $zip"
