from kombu import Connection, Exchange, Queue

from src.core.config import settings
from src.events.schemas import AnalysisRequestedEvent

document_exchange = Exchange(settings.rabbit.document_exchange_name, type="direct")

queue_arguments = {
    "x-dead-letter-exchange": settings.rabbit.document_exchange_name + ".dlx",
    "x-dead-letter-routing-key": settings.rabbit.analysis_routing_key + ".retry",
}

document_analysis_queue = Queue(
    settings.rabbit.analysis_routing_key,
    exchange=document_exchange,
    routing_key=settings.rabbit.analysis_routing_key,
    queue_arguments=queue_arguments,
)


def publish_document_analysis_requested(
    analysis_id: str,
    document_id: int,
    user_id: int,
    request_id: str,
) -> None:
    """
    Publish event: analysis requested
    Sync publication to rabbitmq by kombu
    """
    event = AnalysisRequestedEvent(
        analysis_id=analysis_id,
        document_id=document_id,
        user_id=user_id,
        request_id=request_id,
    )

    with Connection(settings.rabbit.url) as conn:
        producer = conn.Producer()
        producer.publish(
            event.model_dump(),
            exchange=document_exchange,
            routing_key=settings.rabbit.analysis_routing_key,
            declare=[document_analysis_queue],
        )
