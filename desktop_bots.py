"""Frozen entry point for the desktop app: `pacekeeper-bots stock|prediction`.

Runs from a writable working directory (set by the desktop app) that holds
.env, data/ and the SQLite databases.
"""

import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    bot = sys.argv[1] if len(sys.argv) > 1 else ""
    if bot not in ("stock", "prediction"):
        sys.exit("usage: pacekeeper-bots stock|prediction")

    os.makedirs("data", exist_ok=True)
    os.makedirs(os.path.join("prediction_bot", "data"), exist_ok=True)
    load_dotenv(".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if bot == "stock":
        from src.config.settings import settings
        from src.dashboard.app import app
        uvicorn.run(app, host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT)
    else:
        from prediction_bot.src.config.settings import pm_settings
        from prediction_bot.src.dashboard.app import app
        uvicorn.run(app, host="0.0.0.0", port=pm_settings.PM_DASHBOARD_PORT)


if __name__ == "__main__":
    main()
