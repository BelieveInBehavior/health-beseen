"""
FastAPI application entry point.
Lifespan: init MongoDB indexes + Redis pool on startup, close on shutdown.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.cache import close_redis, init_redis
from server.db import close_mongo, init_mongo
from server.routes import assessment, chat, collaboration, events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_mongo()
    await init_redis()
    logging.getLogger(__name__).info("MongoDB + Redis connected")
    yield
    # Shutdown
    await close_redis()
    await close_mongo()


app = FastAPI(title="Health-BeSeen", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessment.router)
app.include_router(chat.router)
app.include_router(collaboration.router)
app.include_router(events.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
