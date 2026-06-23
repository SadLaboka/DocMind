import json
import re

from pydantic import ValidationError

from src.llm.exceptions import LLMException
from src.llm.schemas import AnalysisResult


class BaseMapper:
    def map_response(self, raw_text: str) -> AnalysisResult:
        """Maps raw text from llm-response to analysis result"""
        json_str = self._extract_json_from_text(raw_text)

        json_data = self._parse_json(json_str)
        json_data["raw_response"] = raw_text

        return self._validate_and_normalize(json_data)

    def _extract_json_from_text(self, raw_text: str) -> str:
        """Find json-structure from raw text"""
        markdown_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        match = re.search(markdown_pattern, raw_text, re.DOTALL)

        if match:
            return match.group(1).strip()

        first_brace = raw_text.find("{")
        last_brace = raw_text.rfind("}")

        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return raw_text[first_brace : last_brace + 1]

        raise LLMException(
            message="No JSON found in LLM response",
            error_code="llm_validation_error",
            retryable=True,
        )

    def _parse_json(self, json_str: str) -> dict:
        """Parse json-structure from raw text"""
        try:
            return json.loads(json_str)
        except json.decoder.JSONDecodeError as e:
            raise LLMException(message="Invalid JSON", error_code="llm_validation_error", retryable=True) from e

    def _validate_and_normalize(self, data: dict) -> AnalysisResult:
        """Validate and normalize json-structure"""
        try:
            normalized_data = {k.lower(): v for k, v in data.items()}
            return AnalysisResult.model_validate(normalized_data)
        except ValidationError as e:
            raise LLMException(message="Invalid structure", error_code="llm_validation_error", retryable=True) from e
