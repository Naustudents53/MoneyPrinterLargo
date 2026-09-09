"""Video provider error hierarchy."""


class VideoProviderError(Exception):
    """Base error for video providers."""
    def __init__(self, message: str, provider: str = "", retriable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retriable = retriable


class AuthenticationError(VideoProviderError):
    pass


class RateLimitError(VideoProviderError):
    def __init__(self, message: str, provider: str = "", retry_after_sec: float | None = None):
        super().__init__(message, provider, retriable=True)
        self.retry_after_sec = retry_after_sec


class GenerationError(VideoProviderError):
    pass


class PolicyError(VideoProviderError):
    pass


class NetworkError(VideoProviderError):
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, provider, retriable=True)


class QualityError(VideoProviderError):
    pass


class BudgetExceededError(VideoProviderError):
    pass


class ModelNotAvailableError(VideoProviderError):
    pass
