$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "scripts\build_bots.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location (Join-Path $root "desktop-app")

if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
  Write-Error "Rust is required. Install rustup from https://rustup.rs/"
}

pnpm install
pnpm tauri:build

Write-Host "Built Tauri bundle(s) under desktop-app/src-tauri/target/release/bundle"
