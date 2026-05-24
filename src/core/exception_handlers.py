from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT, HTTP_500_INTERNAL_SERVER_ERROR

from src.core.exceptions import AppBaseError


async def app_base_error_handler(request: Request, exc: AppBaseError) -> JSONResponse:
    return JSONResponse(
        content={
            "code": exc.error_code,
            "detail": exc.message
        },
        status_code=exc.status_code
    )


async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        loc = error.get("loc", ())
        field_parts = [str(part) for part in loc if part not in ("body", "query", "path")]
        field = ".".join(field_parts) if field_parts else "request"

        errors.append({
            "field": field,
            "message": error.get("msg", "Invalid value")
        })

    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        content=({"code": "validation_error",
                  "detail": errors}))


async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"}
    )
