#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

.venv/bin/pip install pyinstaller

.venv/bin/pyinstaller \
  --noconfirm \
  --windowed \
  --name "ClaudeTradeBot" \
  --add-data "src:src" \
  --add-data "prediction_bot:prediction_bot" \
  desktop/launcher.py

echo "Built app at: dist/ClaudeTradeBot.app"
