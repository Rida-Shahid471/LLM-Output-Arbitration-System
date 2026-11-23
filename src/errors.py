class ArbitrationError(Exception):
    """Base exception for expected arbitration failures."""


class ConfigurationError(ArbitrationError):
    pass


class LLMProviderError(ArbitrationError):
    pass


class LLMNonRetryableProviderError(LLMProviderError):
    """A provider rejected a request that retrying unchanged cannot fix."""


class CriticResponseError(ArbitrationError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMResponseError(LLMProviderError):
    pass


class LLMInputLimitError(ArbitrationError):
    """Raised before a request is sent when its configured input budget is exceeded."""


class PersistenceError(ArbitrationError):
    pass


class BatchPersistenceError(PersistenceError):
    """A batch failed to persist atomically and was rolled back."""
