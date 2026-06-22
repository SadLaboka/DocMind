from kombu import Queue, Connection, Exchange
from src.core.config import settings
from src.events.schemas import DocumentTextExtractedEvent

document_exchange = Exchange(settings.rabbit.document_exchange_name, type='direct')

queue_arguments = {
    'x-dead-letter-exchange': settings.rabbit.document_exchange_name + '.dlx',
    'x-dead-letter-routing-key': settings.rabbit.extracted_routing_key + '.retry',
}

document_text_extracted_queue = Queue(
    settings.rabbit.extracted_routing_key,
    exchange=document_exchange,
    routing_key=settings.rabbit.extracted_routing_key,
    queue_arguments=queue_arguments,
)


def publish_document_text_extracted(
        document_id: int,
        mime_type: str,
        user_id: int,
        request_id: str,
) -> None:
    """
    Publish event: text was extracted
    Sync publication to rabbitmq by kombu
    """
    event = DocumentTextExtractedEvent(
        document_id=document_id,
        mime_type=mime_type,
        user_id=user_id,
        request_id=request_id,
    )

    with Connection(settings.rabbit.url) as conn:
        producer = conn.Producer()
        producer.publish(
            event.model_dump(),
            exchange=document_exchange,
            routing_key=settings.rabbit.extracted_routing_key,
            declare=[document_text_extracted_queue],
        )
