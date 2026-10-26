#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/build_bots.py"
cd "$ROOT_DIR/desktop-app"

if ! command -v rustc >/dev/null 2>&1; then
  echo "Rust is required. Install with: curl https://sh.rustup.rs -sSf | sh"
  exit 1
fi

pnpm install
pnpm tauri:build

echo "Built Tauri bundle(s) under: desktop-app/src-tauri/target/release/bundle"
