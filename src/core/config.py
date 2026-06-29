import importlib.metadata
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.enums import LLMProvider

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


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="SERVER_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False


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
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class JWTSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="JWT_")

    private_key_path: str = str(KEYS_DIR / "private.pem")
    public_key_path: str = str(KEYS_DIR / "public.pem")
    timedelta: float = 15
    refresh_timedelta: float = 7
    algorithm: str = "RS256"


class LogsSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="LOGS_")

    dev: bool = True
    level: int = 10


class RabbitSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="RABBITMQ_")

    host: str = "localhost"
    port: int = 5672
    panel_port: int = 15671
    user: str = "guest"
    password: str = ""
    document_exchange_name: str = "documents"
    extracted_routing_key: str = "documents.text.extracted"

    @property
    def url(self) -> str:
        """Returns a ready URL for connecting to RabbitMQ"""
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}"


class MongoSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="MONGO_")

    host: str = "localhost"
    port: int = 27017
    username: str = "guest"
    password: str = ""
    name: str = "DocMind"

    @property
    def url(self) -> str:
        """Returns a ready URL for connecting to Mongo"""
        return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}?authSource=admin"


class RedisSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    max_connections: int = 30


class RateLimitSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="RATE_LIMIT_", extra="ignore")

    global_limit: int = 60
    global_window: int = 60

    login_limit: int = 5
    login_window: int = 60

    register_limit: int = 3
    register_window: int = 60

    documents_post_limit: int = 10
    documents_post_window: int = 60

    documents_get_limit: int = 20
    documents_get_window: int = 60


class InitialPromptSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="PROMPT_", extra="ignore")

    initial_version: str = "v1.0.0"


class LLMSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="LLM_")

    default_provider: LLMProvider = LLMProvider.deepseek


class GeminiSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="GEMINI_")

    api_key: str = ""
    model: str = "gemini-3.1-flash-lite"
    timeout: float = 60.0
    max_tokens: int = 4096
    temperature: float = 0.2


class DeepSeekSettings(SettingsBase):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix="DEEPSEEK_")

    api_key: str = ""
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    timeout: float = 60.0
    max_tokens: int = 8192
    temperature: float = 0.2


class Settings(BaseSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    logs: LogsSettings = Field(default_factory=LogsSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    rabbit: RabbitSettings = Field(default_factory=RabbitSettings)
    mongo: MongoSettings = Field(default_factory=MongoSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    initial_prompt: InitialPromptSettings = Field(default_factory=InitialPromptSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    deepseek: DeepSeekSettings = Field(default_factory=DeepSeekSettings)

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    base_dir: str = BASE_DIR


settings = Settings()
