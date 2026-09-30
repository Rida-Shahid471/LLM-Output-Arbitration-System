class ArbitrationError(Exception):
    """Base exception for the arbitration system."""


class ConfigurationError(ArbitrationError):
    """Raised when project configuration is invalid."""


class LLMProviderError(ArbitrationError):
    """Raised when an LLM provider operation fails."""


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM request times out."""


class LLMResponseError(LLMProviderError):
    """Raised when an LLM response is invalid or unusable."""
    