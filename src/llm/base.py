from abc import abstractmethod, ABC



class BaseLLMService(ABC):
    @abstractmethod
    async def analyze_text(self, text: str, prompt: str):
        """Main logic for analyzing text"""
