import logging
import logging.config
import sys

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer

from src.core.config import settings


class SqlNoiseFilter(logging.Filter):
    """Filters out SQLAlchemy noise records, keeps only meaningful SQL"""

    _MEANINGFUL_PREFIXES = (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "CREATE",
        "DROP",
        "ALTER",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if "sqlalchemy" not in record.name.lower():
            return True

        msg = record.getMessage().strip().upper()
        return any(msg.startswith(prefix) for prefix in self._MEANINGFUL_PREFIXES)


class MultipartDebugFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.levelno < logging.INFO and "multipart" in record.name.lower())


def get_renderer() -> ConsoleRenderer | JSONRenderer:
    """Returns a renderer depending on the environment specified in the settings"""
    return (
        ConsoleRenderer(
            pad_level=False,
            pad_event=0,
            timestamp_key="timestamp",
        )
        if settings.logs.dev
        else JSONRenderer()
    )


def get_processors() -> list:
    """Return a list of processors depending on the environment specified in the settings"""
    return structlog_processors if settings.logs.dev else structlog_processors_prod


def _remove_record_metadata(logger, method_name, event_dict):
    """Removes internal ProcessorFormatter metadata from foreign log records"""
    event_dict.pop("_record", None)
    event_dict.pop("_from_structlog", None)
    return event_dict


timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp")

structlog_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer(),
]

structlog_processors_prod = [
    structlog.contextvars.merge_contextvars,
    timestamper,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer(),
]

stdlib_processors = [
    _remove_record_metadata,
    structlog.stdlib.add_log_level,
    timestamper,
    structlog.processors.ExceptionRenderer(),
]


def setup_logging() -> None:
    """Configures standard logging and structlog with unified output format"""

    renderer = get_renderer()
    processors = get_processors()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog_formatter": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [*stdlib_processors, renderer],
                    "foreign_pre_chain": [structlog.stdlib.add_log_level, timestamper],
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "structlog_formatter",
                },
            },
            "loggers": {
                "root": {
                    "level": settings.logs.level,
                    "handlers": ["default"],
                },
                "uvicorn.error": {
                    "level": settings.logs.level,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": settings.logs.level,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "sqlalchemy.engine.Engine": {
                    "level": 40,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "multipart": {
                    "level": settings.logs.level,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "amqp": {
                    "level": 40,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "kombu": {
                    "level": 40,
                    "handlers": ["default"],
                    "propagate": False,
                },
            },
        }
    )

    sql_filter = SqlNoiseFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sql_filter)

    logging.getLogger("multipart").addFilter(MultipartDebugFilter())

    for handler in logging.root.handlers:
        handler.addFilter(MultipartDebugFilter())

    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=not settings.logs.dev,
    )
