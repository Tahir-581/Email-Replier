# src/llm/client.py
"""
LLM client for vLLM OpenAI-compatible API.

Endpoint: POST https://llm.example.com/v1/chat/completions
Model:    gemma4
Shape:    OpenAI-compatible messages array + model field.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_any,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from src.llm.errors import LLMRequestError, LLMUnavailableError
from src.utils.config import settings

logger = logging.getLogger(__name__)


@dataclass
class _LoopLLMResources:
    client: httpx.AsyncClient
    semaphore: asyncio.Semaphore


_resources_by_loop: dict[int, _LoopLLMResources] = {}


def _build_async_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"Content-Type": "application/json"},
        limits=httpx.Limits(
            max_connections=max(1, settings.LLM_MAX_CONNECTIONS),
            max_keepalive_connections=max(1, settings.LLM_MAX_KEEPALIVE_CONNECTIONS),
        ),
        timeout=float(settings.LLM_TIMEOUT_S),
    )


def _get_loop_resources() -> _LoopLLMResources:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    resources = _resources_by_loop.get(loop_id)
    if resources is None or resources.client.is_closed:
        resources = _LoopLLMResources(
            client=_build_async_client(),
            semaphore=asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENCY)),
        )
        _resources_by_loop[loop_id] = resources
    return resources


async def close_llm_client() -> None:
    loop = asyncio.get_running_loop()
    resources = _resources_by_loop.pop(id(loop), None)
    if resources is not None and not resources.client.is_closed:
        await resources.client.aclose()


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def _is_empty_llm_response(value: object) -> bool:
    """HTTP 200 but no assistant text — treat like a failed fetch and retry."""
    if value is None:
        return True
    return not str(value).strip()


def _normalize_messages_for_provider(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Some Gemma OpenAI-compatible servers reject the `system` role.
    Fold system instructions into the first user message unless explicitly enabled.
    """
    if settings.LLM_SUPPORTS_SYSTEM_ROLE:
        return [dict(message) for message in messages]

    system_parts: list[str] = []
    normalized: list[dict[str, Any]] = []

    for message in messages:
        copied = dict(message)
        if copied.get("role") == "system":
            content = copied.get("content", "")
            if content is not None and str(content).strip():
                system_parts.append(str(content).strip())
            continue
        normalized.append(copied)

    if not system_parts:
        return normalized

    prefix = "System instructions:\n" + "\n\n".join(system_parts)
    for message in normalized:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            message["content"] = f"{prefix}\n\nUser message:\n{content}"
        else:
            normalized.insert(0, {"role": "user", "content": prefix})
        return normalized

    normalized.insert(0, {"role": "user", "content": prefix})
    return normalized


def _response_body_preview(response: httpx.Response, limit: int = 1200) -> str:
    body = response.text.strip()
    if len(body) > limit:
        return body[:limit] + "...<truncated>"
    return body


def _raise_llm_status_error(response: httpx.Response) -> None:
    if response.is_success:
        return

    body = _response_body_preview(response)
    message = (
        f"LLM request failed with HTTP {response.status_code} {response.reason_phrase} "
        f"for {response.request.url}"
    )
    if body:
        message = f"{message}; response body: {body}"

    status_error = httpx.HTTPStatusError(
        message,
        request=response.request,
        response=response,
    )

    if response.status_code == 429 or response.status_code >= 500:
        raise status_error

    raise LLMRequestError(message) from status_error


@retry(
    retry=retry_any(
        retry_if_exception(_is_retryable),
        retry_if_result(_is_empty_llm_response),
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def gamma_chat(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.0,
    tools: list[dict[str, Any]] | None = None,
    timeout: float | None = None,
) -> str:
    """
    Call the vLLM OpenAI-compatible API.

    Returns the assistant message content as a plain string.
    Retries on transport errors and on empty assistant content (same attempt budget).
    Raises httpx.HTTPStatusError or httpx.TimeoutException after retries exhaust.
    """
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": _normalize_messages_for_provider(messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    effective_timeout = timeout or float(settings.LLM_TIMEOUT_S)
    resources = _get_loop_resources()

    async with resources.semaphore:
        response = await resources.client.post(
            settings.LLM_BASE_URL,
            json=payload,
            timeout=effective_timeout,
        )
        _raise_llm_status_error(response)
        data = response.json()

    # Support both OpenAI-style and direct content responses
    choices = data.get("choices")
    if choices and isinstance(choices, list) and len(choices) > 0:
        msg = choices[0].get("message") or {}
        raw = msg.get("content")
        result = "" if raw is None else str(raw)
    else:
        # Fallback: some APIs return content at top level
        content = data.get("content") or data.get("message", {}).get("content", "")
        result = str(content) if content is not None else ""
    
    # Report successful call to health checker
    try:
        from src.llm.health_checker import get_health_checker
        health_checker = get_health_checker()
        health_checker.report_llm_success()
    except ImportError:
        pass
    
    return result


# Health checker integration wrapper
async def gamma_chat_with_health_check(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.0,
    tools: list[dict[str, Any]] | None = None,
    timeout: float | None = None,
) -> str:
    """
    Wrapper around gamma_chat that integrates with the health checker.
    Notifies the health checker of failures for better system-wide pause behavior.
    """
    # Check health before making any LLM call
    try:
        from src.llm.health_checker import is_llm_healthy
        if not await is_llm_healthy():
            # Don't even try to call LLM if health checker says it's down
            raise LLMUnavailableError("LLM service reported as unhealthy - skipping call")
    except ImportError:
        # Health checker not available, proceed with call
        pass
    
    try:
        result = await gamma_chat(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            timeout=timeout,
        )
        # Report successful call to health checker
        try:
            from src.llm.health_checker import get_health_checker
            health_checker = get_health_checker()
            health_checker.report_llm_success()
        except ImportError:
            pass
        return result
    except LLMRequestError:
        raise
    except Exception as exc:
        # Immediately report failure to health checker
        try:
            from src.llm.health_checker import get_health_checker
            health_checker = get_health_checker()
            health_checker.report_llm_failure(exc)
        except ImportError:
            # Health checker not available, just log and continue
            pass
        
        raise LLMUnavailableError(str(exc)) from exc


def _run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - bridge safety
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


def run_coroutine_sync(coro):
    """Run an async coroutine from synchronous code (safe if an event loop is already running)."""
    return _run_sync(coro)


class SyncLLMClient:
    def system_user(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2000,
        temperature: float = 0.0,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return _run_sync(
            gamma_chat_with_health_check(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )


llm = SyncLLMClient()
