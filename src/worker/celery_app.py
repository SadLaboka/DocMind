import logging

from celery import Celery
from celery.signals import worker_init

from src.core.config import settings
from src.core.logging_config import setup_logging

app = Celery("worker", broker=settings.rabbit.url, worker_max_tasks_per_child=50, task_time_limit=240)

app.autodiscover_tasks(["src.worker"])

app.conf.worker_hijack_root_logger = False

logging.getLogger("kombu").setLevel(logging.WARNING)
logging.getLogger("amqp").setLevel(logging.WARNING)
logging.getLogger("celery.worker.heartbeat").setLevel(logging.WARNING)
logging.getLogger("celery.app.trace").setLevel(logging.WARNING)
logging.getLogger("celery.worker.job").setLevel(logging.WARNING)

@worker_init.connect
def configure_logging(**kwargs):
    """Configure logging for the worker"""
    setup_logging()

    logging.getLogger("kombu").setLevel(logging.WARNING)
    logging.getLogger("amqp").setLevel(logging.WARNING)
    logging.getLogger("celery.app.trace").setLevel(logging.WARNING)
    logging.getLogger("celery.worker.job").setLevel(logging.WARNING)
