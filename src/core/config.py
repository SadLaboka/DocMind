import importlib.metadata

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

_PACKAGE_NAME = "docmind"

try:
    APP_NAME = _PACKAGE_NAME
    APP_VERSION = importlib.metadata.version(APP_NAME)
except importlib.metadata.PackageNotFoundError:
    APP_NAME = "dev"
    APP_VERSION = "0.0.0"

ENV_FILE = ".env"
BASE_DIR = Path(__file__).parent.parent


class SettingsBase(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


class DatabaseSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="DB_")

    user: str
    password: str
    name: str
    host: str
    port: int

    @property
    def url(self) -> str:
        """Returns a ready URL for connecting to PostgreSQL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )


class Settings(BaseSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    base_dir: str = BASE_DIR


settings = Settings()
