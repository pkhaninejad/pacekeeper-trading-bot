$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $root "desktop-app")

if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
  Write-Error "Rust is required. Install rustup from https://rustup.rs/"
}

npm install
npx tauri build

Write-Host "Built Tauri bundle(s) under desktop-app/src-tauri/target/release/bundle"
