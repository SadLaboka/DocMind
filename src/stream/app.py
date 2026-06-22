import aio_pika
from aio_pika.abc import AbstractRobustConnection
from faststream import FastStream
from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas.queue import ClassicQueueArgs

from src.core.config import settings
from src.core.logging_config import setup_logging
from src.core.mongo_database import init_mongo_for_worker
from src.llm.gemini.service import GeminiLLMService
from src.repositories.mongo_prompts import MongoPromptsRepository
from src.stream.consumers.document_analysis import DocumentAnalysisConsumer
from src.stream.middleware import RetryLoggingMiddleware

broker = RabbitBroker(settings.rabbit.url, logger=None)

broker.add_middleware(RetryLoggingMiddleware)

app = FastStream(broker)

main_queue_name = settings.rabbit.extracted_routing_key
dead_letter_exchange = settings.rabbit.document_exchange_name + ".dlx"
retry_name = settings.rabbit.extracted_routing_key + ".retry"
dlq_name = settings.rabbit.extracted_routing_key + ".dlq"

documents_exchange = RabbitExchange(settings.rabbit.document_exchange_name, type=ExchangeType.DIRECT)

main_queue_args: ClassicQueueArgs = {
    "x-dead-letter-exchange": dead_letter_exchange,
    "x-dead-letter-routing-key": retry_name,
}
main_queue = RabbitQueue(
    name=main_queue_name,
    routing_key=main_queue_name,
    arguments=main_queue_args,
)

retry_queue_args = {
    "x-dead-letter-exchange": settings.rabbit.document_exchange_name,
    "x-dead-letter-routing-key": main_queue_name,
    "x-message-ttl": 60000,
}

llm_service = GeminiLLMService(
    api_key=settings.gemini.api_key,
    model=settings.gemini.model,
    timeout=settings.gemini.timeout,
    max_tokens=settings.gemini.max_tokens,
    temperature=settings.gemini.temperature,
)
prompt_repo = MongoPromptsRepository()

analysis_consumer = DocumentAnalysisConsumer(
    llm_service=llm_service,
    prompt_repo=prompt_repo,
)


@app.on_startup
async def on_startup():
    """Setup FastStream on startup"""
    setup_logging()

    await init_mongo_for_worker()

    connection: AbstractRobustConnection = await aio_pika.connect_robust(settings.rabbit.url)
    async with connection:
        channel = await connection.channel()

        dlx_exchange = await channel.declare_exchange(
            dead_letter_exchange,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        retry_queue = await channel.declare_queue(retry_name, durable=True, arguments=retry_queue_args)
        await retry_queue.bind(dlx_exchange, routing_key=settings.rabbit.extracted_routing_key + ".retry")

        await channel.declare_queue(
            dlq_name,
            durable=True,
        )


@broker.subscriber(queue=main_queue, exchange=documents_exchange)
async def handle_document_analysis(message: dict) -> None:
    """FastStream entrypoint for document analysis"""
    await analysis_consumer(message)
