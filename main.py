import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response

from src.core.config import settings
from src.api.documents import router as documents_router
from src.api.users import router as users_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/openapi",
    openapi_url="/openapi.json",
    redoc_url="/redoc",
)

app.include_router(documents_router)
app.include_router(users_router)


@app.get("/")
def root():
    return Response(status_code=200)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )
