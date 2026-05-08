$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

.venv\Scripts\pip install pyinstaller

.venv\Scripts\pyinstaller.exe `
  --noconfirm `
  --windowed `
  --name "ClaudeTradeBot" `
  --add-data "src;src" `
  --add-data "prediction_bot;prediction_bot" `
  desktop/launcher.py

Write-Host "Built app at: dist/ClaudeTradeBot"
