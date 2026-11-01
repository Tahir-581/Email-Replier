"""
Process multiple pending emails with bounded parallelism.

Each email still runs the full LangGraph pipeline independently. Concurrency is
limited by EMAIL_BATCH_CONCURRENCY (default 3) so LLM and DB load stay predictable.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal

from src.db.session import get_pending_emails, update_email_status
from src.llm.errors import LLMError
from src.pipeline.graph import pipeline
from src.utils.config import settings

logger = logging.getLogger(__name__)

OutcomeKind = Literal["ok", "error", "deferred"]


@dataclass(frozen=True)
class _EmailOutcome:
    email_id: str
    kind: OutcomeKind
    result: dict[str, Any] | None = None
    error: BaseException | None = None


def _resolve_concurrency(concurrency: int | None, email_count: int) -> int:
    if email_count <= 0:
        return 1
    limit = concurrency if concurrency is not None else settings.EMAIL_BATCH_CONCURRENCY
    return max(1, min(int(limit), email_count))


def _process_one(email: dict[str, Any]) -> _EmailOutcome:
    email_id = email["email_id"]
    try:
        result = pipeline.invoke(email)
        if result.get("status") == "error":
            return _EmailOutcome(email_id=email_id, kind="error", result=result)
        return _EmailOutcome(email_id=email_id, kind="ok", result=result)
    except LLMError as exc:
        update_email_status(email_id, "pending")
        return _EmailOutcome(email_id=email_id, kind="deferred", error=exc)
    except Exception as exc:
        return _EmailOutcome(email_id=email_id, kind="error", error=exc)


def _log_outcome(email: dict[str, Any], outcome: _EmailOutcome) -> None:
    from_addr = email.get("from_addr", "")
    if outcome.kind == "ok" and outcome.result is not None:
        result = outcome.result
        logger.info(
            "Done: %s | from=%s | intent=%s (%s) | profile=%s | sent=%s | status=%s",
            outcome.email_id,
            from_addr,
            result.get("intent_id"),
            result.get("intent_label"),
            result.get("profile_type"),
            result.get("sent"),
            result.get("status"),
        )
    elif outcome.kind == "deferred":
        logger.error(
            "LLM failed for %s | from=%s — reset to pending for retry. Error: %s",
            outcome.email_id,
            from_addr,
            outcome.error,
        )
    else:
        logger.error(
            "Pipeline failed for %s | from=%s: %s",
            outcome.email_id,
            from_addr,
            outcome.error,
            exc_info=outcome.error is not None,
        )


def process_email_batch(
    emails: list[dict[str, Any]] | None = None,
    *,
    concurrency: int | None = None,
) -> dict[str, int]:
    """
    Run the agent pipeline for each email with bounded thread parallelism.

    Returns counts: total, processed, errors, deferred.
    ``deferred`` is the number of emails reset to ``pending`` after an LLMError.
    """
    batch = list(emails) if emails is not None else get_pending_emails()
    total = len(batch)

    if not batch:
        return {"total": 0, "processed": 0, "errors": 0, "deferred": 0}

    workers = _resolve_concurrency(concurrency, total)
    logger.info(
        "Processing %d email(s) with batch concurrency=%d.",
        total,
        workers,
    )

    processed = 0
    errors = 0
    deferred = 0

    def consume(outcome: _EmailOutcome, email: dict[str, Any]) -> None:
        nonlocal processed, errors, deferred
        _log_outcome(email, outcome)
        if outcome.kind == "ok":
            processed += 1
        elif outcome.kind == "deferred":
            deferred += 1
        else:
            errors += 1

    if workers == 1:
        for email in batch:
            logger.info("Processing: %s | from=%s", email["email_id"], email.get("from_addr"))
            consume(_process_one(email), email)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="email-batch") as pool:
            futures = {pool.submit(_process_one, email): email for email in batch}
            for future in as_completed(futures):
                email = futures[future]
                try:
                    outcome = future.result()
                except Exception as exc:
                    outcome = _EmailOutcome(email_id=email["email_id"], kind="error", error=exc)
                consume(outcome, email)

    logger.info(
        "Batch complete | total=%d | processed=%d | errors=%d | deferred=%d",
        total,
        processed,
        errors,
        deferred,
    )
    return {
        "total": total,
        "processed": processed,
        "errors": errors,
        "deferred": deferred,
    }
