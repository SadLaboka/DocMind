from abc import ABC, abstractmethod


class BaseLLMService(ABC):
    @abstractmethod
    async def analyze_text(self, text: str, prompt: str):
        """Main logic for analyzing text"""
