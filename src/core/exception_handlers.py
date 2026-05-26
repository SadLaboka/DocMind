import structlog

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT, HTTP_500_INTERNAL_SERVER_ERROR

from src.core.exceptions import AppBaseError

log = structlog.get_logger(__name__)


async def app_base_error_handler(request: Request, exc: AppBaseError) -> JSONResponse:
    """Handler for client exceptions"""

    log_method = log.warning if exc.status_code < 500 else log.error

    log_method(
        "service_error",
        error_code=exc.error_code,
        status_code=exc.status_code,
        request_id=getattr(request.state, "request_id", None),
        client_ip=getattr(request.state, "client_ip", None),
        method=request.method,
        path=request.url.path,
        **exc.log_context
    )

    return JSONResponse(
        content={
            "code": exc.error_code,
            "detail": exc.message
        },
        status_code=exc.status_code
    )


async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler for validation exceptions"""
    errors = []
    for error in exc.errors():
        loc = error.get("loc", ())
        field_parts = [str(part) for part in loc if part not in ("body", "query", "path")]
        field = ".".join(field_parts) if field_parts else "request"

        errors.append({
            "field": field,
            "message": error.get("msg", "Invalid value")
        })

    log.warning(
        "validation_error",
        request_id=getattr(request.state, "request_id", None),
        client_ip=getattr(request.state, "client_ip", None),
        method=request.method,
        path=request.url.path,
        errors=errors
    )

    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        content=({"code": "validation_error",
                  "detail": errors}))


async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for unhandled exceptions"""
    log.critical(
        "unhandled_exception",
        request_id=getattr(request.state, "request_id", None),
        client_ip=getattr(request.state, "client_ip", None),
        method=request.method,
        path=request.url.path,
        exc_info=True
    )

    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"}
    )
