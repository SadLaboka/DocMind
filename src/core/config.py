import importlib.metadata
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_NAME = "docmind"

try:
    APP_NAME = _PACKAGE_NAME
    APP_VERSION = importlib.metadata.version(APP_NAME)
except importlib.metadata.PackageNotFoundError:
    APP_NAME = "dev"
    APP_VERSION = "0.0.0"

ENV_FILE = ".env"
BASE_DIR = str(Path(__file__).parent.parent)
KEYS_DIR = Path(BASE_DIR).parent / "keys"


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


class JWTSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="JWT_")

    private_key_path: str = str(KEYS_DIR / "private.pem")
    public_key_path: str = str(KEYS_DIR / "public.pem")
    timedelta: float = 15
    refresh_timedelta: float = 7
    algorithm: str = "RS256"


class Settings(BaseSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    base_dir: str = BASE_DIR


settings = Settings()
