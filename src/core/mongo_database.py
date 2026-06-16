from contextlib import asynccontextmanager
from pymongo import AsyncMongoClient
from beanie import init_beanie
from fastapi import FastAPI

from src.core.config import settings
from src.models.mongo_documents import MongoDocument


@asynccontextmanager
async def init_mongo_db(app: FastAPI):
    client = AsyncMongoClient(settings.mongo.url)
    database = client[settings.mongo.name]

    await init_beanie(
        database=database,
        document_models=[MongoDocument],
    )

    yield
