import logging
import logging.config
import sys

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer

from src.core.config import settings


def get_renderer() -> ConsoleRenderer | JSONRenderer:
    """Returns a renderer depending on the environment specified in the settings"""
    return ConsoleRenderer() if settings.logs.dev else JSONRenderer()


timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

structlog_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    timestamper,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer()
]

stdlib_processors = [
    structlog.stdlib.add_log_level,
    timestamper,
    structlog.processors.ExceptionRenderer()
]


def setup_logging() -> None:
    """Configures standard logging and structlog with unified output format"""
    renderer = get_renderer()

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            "structlog_formatter": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": stdlib_processors + [renderer],
                "foreign_pre_chain": [
                    structlog.stdlib.add_log_level,
                    timestamper
                ],
            },
        },
        'handlers': {
            "default": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "structlog_formatter",
            },
        },
        'loggers': {
            "root": {
                "level": settings.logs.level,
                "handlers": ["default"],
            },
            "uvicorn.error": {
                "level": 20,
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": 20,
                "handlers": ["default"],
                "propagate": False,
            },
        },
    })

    structlog.configure(
        processors=structlog_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=not settings.logs.dev
    )
