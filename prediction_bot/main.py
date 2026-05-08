import logging
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Allow running as a script: `.venv/bin/python prediction_bot/main.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv()
from prediction_bot.src.config.settings import pm_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

if __name__ == "__main__":
    uvicorn.run(
        "prediction_bot.src.dashboard.app:app",
        host="0.0.0.0",
        port=pm_settings.PM_DASHBOARD_PORT,
        reload=True,
    )
