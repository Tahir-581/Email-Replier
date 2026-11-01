# src/utils/retry.py
"""
Retry wrappers for LLM and external API calls.
All agents and tools import from here — never call the LLM directly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.llm.client import gamma_chat_with_health_check

logger = logging.getLogger(__name__)


# ── LLM retry ─────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def llm_with_retry(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """
    Call the Gamma LLM with exponential backoff (3 attempts).
    After 3 failures, re-raises — the calling agent must handle gracefully.
    """
    return await gamma_chat_with_health_check(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        tools=tools,
    )


# ── API retry ─────────────────────────────────────────────────

def _is_retriable_api_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.TimeoutException, ConnectionError))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception(_is_retriable_api_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def api_with_retry(
    url: str,
    method: str = "GET",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Async HTTP call with rate-limit-aware retry (429/5xx).
    Used by the websearch fallback — sync tools have their own retry logic.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        response = await getattr(client, method.lower())(url, **kwargs)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
