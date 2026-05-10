from pydantic_settings import BaseSettings, SettingsConfigDict
import importlib.metadata

_PACKAGE_NAME = "DocuMind"

try:
    APP_NAME = _PACKAGE_NAME
    APP_VERSION = importlib.metadata.version(APP_NAME)
except importlib.metadata.PackageNotFoundError:
    APP_NAME = "dev"
    APP_VERSION = "0.0.0"


class Settings(BaseSettings):
    title_name: str = APP_NAME
    title_version: str = APP_VERSION

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
