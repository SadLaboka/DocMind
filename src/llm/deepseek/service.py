import asyncio

from openai import APIError, AsyncOpenAI

from src.llm.base import BaseLLMService
from src.llm.base_mapper import BaseMapper
from src.llm.exceptions import LLMException
from src.llm.schemas import AnalysisResult


class DeepSeekLLMService(BaseLLMService):
    def __init__(
        self, api_key: str, model: str, timeout: float, max_tokens: int, temperature: float, base_url: str
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        self._mapper = BaseMapper()

    async def analyze_text(self, text: str, prompt: str) -> AnalysisResult:

        if "{text}" not in prompt:
            raise LLMException(
                message="Prompt configuration error",
                error_code="prompt_config_error",
                retryable=False,
            )

        prompt_with_text = prompt.replace("{text}", text)

        messages = [
            {"role": "system", "content": prompt_with_text},
            {"role": "user", "content": ""},
        ]

        try:
            raw_response = await self._call_deepseek_api(messages=messages)
        except TimeoutError as e:
            raise LLMException(message="Request timeout", error_code="llm_timeout", retryable=True) from e
        except APIError as e:
            if e.code and e.code.startswith("5"):
                raise LLMException(message="Provider error", error_code="llm_provider_error", retryable=True) from e
            elif e.code == "429":
                raise LLMException(message="Rate limit exceeded", error_code="llm_rate_limit", retryable=True) from e
            else:
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

    async def _call_deepseek_api(self, messages: list[dict[str, str]]) -> str | None:
        """Makes an async API request to generate analysis with using a model"""
        response = await asyncio.wait_for(
            self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=messages,
            ),
            timeout=self.timeout,
        )
        return response.choices[0].message.content
