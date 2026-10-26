"""Freeze both bots into one PyInstaller binary for the Tauri sidecar.

Usage (from repo root, with requirements + pyinstaller installed):
    python scripts/build_bots.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = [
    "src/dashboard/templates",
    "src/dashboard/static",
    "src/data/prediction_markets_config.yaml",
    "prediction_bot/src/dashboard/templates",
    "prediction_bot/config/llm_providers.json",
]


def target_triple() -> str:
    out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    return next(line.split(": ")[1] for line in out.splitlines() if line.startswith("host: "))


def main() -> None:
    args = [
        sys.executable, "-m", "PyInstaller", "desktop_bots.py",
        "--name", "pacekeeper-bots", "--onefile", "--noconfirm", "--clean",
        "--collect-data", "litellm",
        "--collect-submodules", "uvicorn",
        "--hidden-import", "tiktoken_ext.openai_public",
    ]
    for path in DATA:
        dest = path if (ROOT / path).is_dir() else str(Path(path).parent)
        args += ["--add-data", f"{path}{os.pathsep}{dest}"]
    subprocess.run(args, cwd=ROOT, check=True)

    ext = ".exe" if sys.platform == "win32" else ""
    out_dir = ROOT / "desktop-app/src-tauri/binaries"
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"pacekeeper-bots-{target_triple()}{ext}"
    shutil.copy2(ROOT / "dist" / f"pacekeeper-bots{ext}", dest)
    print(f"sidecar: {dest}")


if __name__ == "__main__":
    main()
