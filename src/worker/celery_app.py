from celery import Celery

from src.core.config import settings

app = Celery('worker', broker=settings.rabbit.url)

app.autodiscover_tasks(["src.worker"])
