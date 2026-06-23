import asyncio

import structlog
from google import genai
from google.genai.errors import ClientError, ServerError
from google.genai.types import GenerateContentConfig

from src.llm.base import BaseLLMService
from src.llm.exceptions import LLMException
from src.llm.base_mapper import BaseMapper
from src.llm.schemas import AnalysisResult

logger = structlog.get_logger(__name__)


class GeminiLLMService(BaseLLMService):
    def __init__(self, api_key: str, model: str, timeout: float, max_tokens: int, temperature: float) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = genai.Client(api_key=self.api_key).aio
        self._mapper = BaseMapper()

    async def analyze_text(self, text: str, prompt: str) -> AnalysisResult:

        if "{text}" not in prompt:
            raise LLMException(
                message="Prompt configuration error",
                error_code="prompt_config_error",
                retryable=False,
            )

        prompt_with_text = prompt.replace("{text}", text)

        config = GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )

        try:
            raw_response = await self._call_gemini_api(
                model=self.model,
                contents=prompt_with_text,
                config=config,
            )
        except asyncio.TimeoutError as e:
            raise LLMException(message="Request timeout", error_code="llm_timeout", retryable=True) from e
        except ServerError as e:
            raise LLMException(message="Provider error", error_code="llm_provider_error", retryable=True) from e
        except ClientError as e:
            if e.code == 429 or "RESOURCE_EXHAUSTED" in str(e):
                raise LLMException(message="Rate limit exceeded", error_code="llm_rate_limit", retryable=True) from e

            raise LLMException(
                message=getattr(e, "message", str(e)), error_code="llm_config_error", retryable=False
            ) from e

        if not raw_response:
            raise LLMException(
                message="Generating content error",
                error_code="generate_content_error",
                retryable=True,
            )

        return self._mapper.map_response(raw_response)

    async def _call_gemini_api(self, model: str, contents: str, config: GenerateContentConfig) -> str | None:
        """Makes an async API request to generate analysis with using a model"""
        response = await asyncio.wait_for(
            self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            ),
            timeout=self.timeout,
        )

        return response.text
