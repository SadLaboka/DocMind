class LLMException(Exception):
    """Exception for LLM exceptions"""

    def __init__(self, message: str, error_code: str, retryable: bool = True):
        self.message = message
        self.error_code = error_code
        self.retryable = retryable
