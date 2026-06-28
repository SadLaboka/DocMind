from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.core.mongo_database import init_mongo_db
from src.core.redis import init_redis, close_redis


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Combined lifespan for all services"""
    async with init_mongo_db(app):
        await init_redis()
        yield
        await close_redis()
