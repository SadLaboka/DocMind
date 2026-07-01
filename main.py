import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.auth import router as auth_router
from src.api.documents import router as documents_router
from src.api.users import router as users_router
from src.core.config import settings
from src.core.exception_handlers import app_base_error_handler, exception_handler, request_validation_error_handler
from src.core.exceptions import AppBaseError
from src.core.logging_config import setup_logging
from core.middlewares.request_context import RequestContextMiddleware
from src.core.lifespan import app_lifespan

setup_logging()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=app_lifespan,
    docs_url="/openapi",
    openapi_url="/openapi.json",
    redoc_url="/redoc",
)

app.add_middleware(RequestContextMiddleware)
app.include_router(documents_router)
app.include_router(users_router)
app.include_router(auth_router)
app.add_exception_handler(AppBaseError, app_base_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, exception_handler)


@app.get("/")
def root():
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
    )
