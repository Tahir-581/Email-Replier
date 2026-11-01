# src/llm/health_checker.py
"""
LLM Health Checker - monitors LLM service availability and pauses processing when down.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from src.utils.config import settings

logger = logging.getLogger(__name__)


def _response_body_preview(response: httpx.Response, limit: int = 1200) -> str:
    body = response.text.strip()
    if len(body) > limit:
        return body[:limit] + "...<truncated>"
    return body


class LLMHealthChecker:
    """Monitors LLM service health and provides pause functionality when unavailable."""
    
    def __init__(self) -> None:
        self._last_check_time: float = 0
        self._last_status: bool = True  # Assume healthy initially
        self._normal_check_interval: float = 60.0  # Check every 60 seconds when healthy
        self._failure_check_interval: float = 30.0  # Check every 30 seconds when failed
        self._failure_count: int = 0
        self._max_failures: int = 3  # Allow 3 failures before pausing (for remote LLM)
        self._pause_until: float = 0  # Unix timestamp when pause ends
        self._base_pause_duration: float = 30.0  # 30 seconds base pause (shorter for remote LLM)
        self._max_pause_duration: float = 300.0  # 5 minutes max pause
        self._agents_idle: bool = False  # Track if agents are in idle mode
        self._last_successful_call_time: float = 0  # Track actual successful LLM calls
        self._success_validity_seconds: float = 30.0  # Successful call proves health for 30s
        
    async def is_healthy(self) -> bool:
        """Check if LLM service is healthy, using cached result if recent."""
        # Health check can be disabled for self-hosted remote LLMs
        if not settings.LLM_HEALTH_CHECK_ENABLED:
            return True
            
        current_time = time.time()
        
        # If a real LLM call succeeded recently, consider it healthy
        if current_time - self._last_successful_call_time < self._success_validity_seconds:
            if not self._last_status:
                logger.info("LLM service recovered (based on successful call) - resuming normal operation")
                self._last_status = True
                self._failure_count = 0
                self._agents_idle = False
            return True
        
        # Determine check interval based on current status
        check_interval = self._failure_check_interval if not self._last_status else self._normal_check_interval
        
        # If we're in a pause period, respect it
        if current_time < self._pause_until:
            logger.info(
                "LLM service still paused until %s (remaining: %.1fs) - agents in idle mode",
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._pause_until)),
                self._pause_until - current_time
            )
            self._agents_idle = True
            return False
            
        # Check if we need to refresh the health status
        if current_time - self._last_check_time > check_interval:
            await self._refresh_health_status()
            
        # Update agent idle mode based on health status
        if self._last_status:
            if self._agents_idle:
                logger.info("LLM service recovered - agents can resume processing")
                self._agents_idle = False
        else:
            if not self._agents_idle:
                logger.warning("LLM service unhealthy - switching all agents to idle mode")
                self._agents_idle = True
            
        return self._last_status
    
    async def _refresh_health_status(self) -> None:
        """Perform actual health check against LLM service."""
        current_time = time.time()
        self._last_check_time = current_time
        
        try:
            # Simple health check - send a minimal request
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.LLM_BASE_URL,
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "temperature": 0.0,
                        "stream": False,
                    },
                    timeout=10.0
                )
                if response.is_error:
                    logger.warning(
                        "LLM health check returned HTTP %s %s; response body: %s",
                        response.status_code,
                        response.reason_phrase,
                        _response_body_preview(response),
                    )
                response.raise_for_status()
                
            # If we get here, the service is healthy
            if not self._last_status:
                logger.info("LLM service recovered - resuming normal operation")
            
            self._last_status = True
            self._failure_count = 0
            
        except Exception as exc:
            self._failure_count += 1
            logger.warning(
                "LLM health check failed (attempt %d/%d): %s",
                self._failure_count, self._max_failures, exc
            )
            
            # Only mark as unhealthy after multiple failures (more graceful)
            if self._failure_count >= self._max_failures:
                self._last_status = False
                self._trigger_pause()
    
    def report_llm_failure(self, error: Exception) -> None:
        """Report an LLM failure from an agent call."""
        self._failure_count += 1
        logger.error(
            "LLM failure reported by agent (attempt %d): %s",
            self._failure_count, error
        )
        
        # Only mark as unhealthy after multiple failures (more graceful)
        if self._failure_count >= self._max_failures:
            self._last_status = False
            self._agents_idle = True
            self._trigger_pause()
    
    def report_llm_success(self) -> None:
        """Report a successful LLM call from an agent.
        
        This acts as a health proof - if real requests are succeeding,
        the LLM is healthy and we don't need to run the ping health check.
        """
        current_time = time.time()
        was_healthy = self._last_status
        
        self._last_successful_call_time = current_time
        self._last_check_time = current_time  # Also update to skip ping check
        
        if not was_healthy:
            logger.info("LLM service recovered (successful call detected) - resuming normal operation")
        
        self._last_status = True
        self._failure_count = 0
        self._pause_until = 0  # Clear any pause
        self._agents_idle = False
    
    def _trigger_pause(self) -> None:
        """Trigger a pause period with exponential backoff."""
        # Calculate pause duration with exponential backoff
        pause_duration = min(
            self._base_pause_duration * (2 ** (self._failure_count - self._max_failures)),
            self._max_pause_duration
        )
        
        self._pause_until = time.time() + pause_duration
        
        logger.error(
            "LLM service unavailable after %d failures - pausing processing for %.1f minutes until %s",
            self._failure_count,
            pause_duration / 60.0,
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._pause_until))
        )
    
    def get_pause_remaining_seconds(self) -> float:
        """Get remaining pause time in seconds."""
        return max(0.0, self._pause_until - time.time())
    
    def are_agents_idle(self) -> bool:
        """Check if all agents should be in idle mode."""
        return self._agents_idle
    
    def force_health_check(self) -> None:
        """Force a health check on next call to is_healthy()."""
        self._last_check_time = 0


# Global health checker instance
_health_checker: Optional[LLMHealthChecker] = None


def get_health_checker() -> LLMHealthChecker:
    """Get the global LLM health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = LLMHealthChecker()
    return _health_checker


async def is_llm_healthy() -> bool:
    """Convenience function to check LLM health."""
    return await get_health_checker().is_healthy()


async def are_agents_idle() -> bool:
    """Convenience function to check if agents should be in idle mode."""
    return get_health_checker().are_agents_idle()


async def wait_for_llm_recovery(max_wait_minutes: int = 30) -> bool:
    """
    Wait for LLM service to recover, with timeout.
    
    Returns:
        True if LLM recovered, False if timeout reached
    """
    health_checker = get_health_checker()
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    
    logger.info("Waiting for LLM service recovery...")
    
    while time.time() - start_time < max_wait_seconds:
        if await health_checker.is_healthy():
            logger.info("LLM service recovered!")
            return True
            
        remaining = max_wait_seconds - (time.time() - start_time)
        logger.info(
            "LLM still down, waiting %.1f more seconds (pause remaining: %.1fs)",
            remaining,
            health_checker.get_pause_remaining_seconds()
        )
        
        # Sleep for a short interval before checking again
        await asyncio.sleep(30.0)  # Check every 30 seconds
    
    logger.warning("LLM service did not recover within %d minutes", max_wait_minutes)
    return False


# Decorator for adding health checking to existing functions
def with_llm_health_check(agent_name: str = None):
    """
    Decorator that adds LLM health checking to any async function.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Check LLM health before proceeding
            health_status = await is_llm_healthy()
            agents_idle = await are_agents_idle()
            
            if not health_status or agents_idle:
                logger.info(
                    "[%s] Skipping %s - LLM service unavailable (healthy=%s, idle=%s)", 
                    agent_name or 'unknown',
                    func.__name__,
                    health_status,
                    agents_idle
                )
                return {
                    "status": "idle",
                    "reason": "LLM service unavailable - agent in idle mode",
                    "function": func.__name__,
                    "agent": agent_name or 'unknown',
                }
            
            # Proceed with function execution
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
