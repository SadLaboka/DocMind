import asyncio
import sys
from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
import structlog

from src.core.config import settings
from src.core.logging_config import setup_logging
from src.models.mongo_prompts import Prompt
from src.repositories.mongo_prompts import MongoPromptsRepository

logger = structlog.get_logger(__name__)

INITIAL_PROMPT_VERSION = settings.prompt.initial_version
INITIAL_PROMPT_TYPE = "document_analysis"
INITIAL_PROMPT_CONTENT = settings.prompt.initial_content


async def init_mongo() -> AsyncMongoClient:
    """Init mongo for script"""
    client = AsyncMongoClient(settings.mongo.url)
    database = client[settings.mongo.name]
    await init_beanie(
        database=database,
        document_models=[Prompt],
    )
    return client


async def seed_prompt() -> None:
    """Creates prompt if active prompt isn't exists"""
    prompt_repo = MongoPromptsRepository()

    existing_prompt = await prompt_repo.get_active_prompt(INITIAL_PROMPT_TYPE)

    if existing_prompt:
        logger.info(
            "seed_prompt_already_exists",
            version=existing_prompt.version,
            prompt_type=INITIAL_PROMPT_TYPE,
        )
        return

    try:
        await prompt_repo.create_prompt(
            version=INITIAL_PROMPT_VERSION,
            prompt_type=INITIAL_PROMPT_TYPE,
            content=INITIAL_PROMPT_CONTENT.strip(),
        )
        logger.info(
            "seed_prompt_created",
            version=INITIAL_PROMPT_VERSION,
            prompt_type=INITIAL_PROMPT_TYPE,
        )
    except DuplicateKeyError:
        logger.warning(
            "seed_prompt_duplicate",
            version=INITIAL_PROMPT_VERSION,
            prompt_type=INITIAL_PROMPT_TYPE,
        )


async def main() -> None:
    setup_logging()

    client: AsyncMongoClient | None = None

    try:
        client = await init_mongo()
        await seed_prompt()

    except ConnectionFailure as err:
        logger.error(
            "seed_prompt_connection_failed",
            error_code="mongo_connection_error",
            error_detail=str(err),
        )
        sys.exit(1)

    except Exception as err:
        logger.error(
            "seed_prompt_unexpected_error",
            error_code="seed_error",
            error_detail=str(err),
            error_type=type(err).__name__,
        )
        sys.exit(1)

    finally:
        if client:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
