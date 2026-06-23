from src.core.config import Settings
from src.core.enums import LLMProvider
from src.llm.base import BaseLLMService
from src.llm.deepseek.service import DeepSeekLLMService
from src.llm.exceptions import LLMException
from src.llm.gemini.service import GeminiLLMService


class LLMServiceFactory:
    """Factory for creating LLM service instances based on provider"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(self, provider: str) -> BaseLLMService:
        """Creates LLM service based on provider name"""
        try:
            provider_enum = LLMProvider(provider)
        except ValueError as e:
            available_providers = [p.value for p in LLMProvider]
            raise LLMException(
                message=f"Unknown LLM provider: {provider}. Available: {', '.join(available_providers)}",
                error_code="llm_unknown_provider",
                retryable=False,
            ) from e

        if provider_enum == LLMProvider.gemini:
            return GeminiLLMService(
                api_key=self.settings.gemini.api_key,
                model=self.settings.gemini.model,
                timeout=self.settings.gemini.timeout,
                max_tokens=self.settings.gemini.max_tokens,
                temperature=self.settings.gemini.temperature,
            )

        if provider_enum == LLMProvider.deepseek:
            return DeepSeekLLMService(
                api_key=self.settings.deepseek.api_key,
                model=self.settings.deepseek.model,
                base_url=self.settings.deepseek.base_url,
                timeout=self.settings.deepseek.timeout,
                max_tokens=self.settings.deepseek.max_tokens,
                temperature=self.settings.deepseek.temperature,
            )

        raise LLMException(
            message=f"Provider {provider_enum.value} is not implemented",
            error_code="llm_provider_not_implemented",
            retryable=False,
        )
