from __future__ import annotations


class LLMError(RuntimeError):
    """Base exception for LLM failures that should stop the pipeline batch."""


class LLMRequestError(LLMError):
    """The LLM rejected the request or configuration."""


class LLMUnavailableError(LLMError):
    """The LLM service is unavailable or temporarily paused."""
