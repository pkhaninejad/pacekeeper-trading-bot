import logging
import uvicorn
from dotenv import load_dotenv
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
