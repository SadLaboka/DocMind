from contextlib import asynccontextmanager
from pymongo import AsyncMongoClient
from beanie import init_beanie
from fastapi import FastAPI

from src.core.config import settings
from src.models.mongo_documents import MongoDocument


@asynccontextmanager
async def init_mongo_db(app: FastAPI):
    """Init mongo for main app"""
    client = AsyncMongoClient(settings.mongo.url)
    database = client[settings.mongo.name]

    await init_beanie(
        database=database,
        document_models=[MongoDocument],
    )

    yield


async def init_mongo_for_worker() -> None:
    """Init mongo for celery worker"""
    client = AsyncMongoClient(settings.mongo.url)
    database = client[settings.mongo.name]
    await init_beanie(
        database=database,
        document_models=[MongoDocument],
    )
