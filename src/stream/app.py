from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitExchange, ExchangeType, RabbitQueue
from faststream.rabbit.schemas.queue import ClassicQueueArgs

from src.core.config import settings
from src.core.logging_config import setup_logging
from src.core.mongo_database import init_mongo_for_worker
from src.stream.middleware import RetryLoggingMiddleware

broker = RabbitBroker(settings.rabbit.url)

broker.add_middleware(RetryLoggingMiddleware)

app = FastStream(broker)


@app.on_startup
async def on_startup():
    setup_logging()

    await init_mongo_for_worker()

main_queue_name = settings.rabbit.extracted_routing_key
dead_letter_exchange = settings.rabbit.document_exchange_name + ".dlx"
retry_name = settings.rabbit.extracted_routing_key + ".retry"
dlq_name = settings.rabbit.extracted_routing_key + ".dlq"

documents_exchange = RabbitExchange(settings.rabbit.document_exchange_name, type=ExchangeType.DIRECT)
dlx_exchange = RabbitExchange(dead_letter_exchange, type=ExchangeType.DIRECT)

main_queue_args: ClassicQueueArgs = {
    "x-dead-letter-exchange": dead_letter_exchange,
    "x-dead-letter-routing-key": retry_name,
}
main_queue = RabbitQueue(
    name=main_queue_name,
    routing_key=main_queue_name,
    arguments=main_queue_args,
)

retry_queue_args: ClassicQueueArgs = {
    "x-dead-letter-exchange": settings.rabbit.document_exchange_name,
    "x-dead-letter-routing-key": main_queue_name,
}
retry_queue = RabbitQueue(
    name=retry_name,
    routing_key=retry_name,
    arguments=retry_queue_args,
)

dlq_queue = RabbitQueue(
    name=dlq_name,
    routing_key=dlq_name,
)
