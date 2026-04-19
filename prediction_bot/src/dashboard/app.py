import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from prediction_bot.src.api.models import PMBotStatus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Prediction Market Bot", lifespan=lifespan)


@app.get("/api/status")
async def get_status():
    return JSONResponse(PMBotStatus().model_dump(mode="json"))
