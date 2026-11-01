"""Passthrough agent: persists detected intents to JSON and logs labels."""

from __future__ import annotations

import logging

from src.pipeline.state import EmailState
from src.utils.intent_store import save_intents_to_json

logger = logging.getLogger(__name__)


def intent_persister(state: EmailState) -> EmailState:
    email_id = state.get("email_id", "") or ""
    raw_intents = state.get("detected_intents")
    detected_intents: list[dict] = raw_intents if isinstance(raw_intents, list) else []

    summary = state.get("email_summary") or ""
    raw_concerns = state.get("detected_concerns")
    concerns: list[str] = raw_concerns if isinstance(raw_concerns, list) else []

    save_intents_to_json(email_id, detected_intents, summary, concerns)

    labels = [
        str(item.get("intent_label", ""))
        for item in detected_intents
        if isinstance(item, dict)
    ]
    logger.info(
        "[IntentPersister] email_id=%s | detected_intents_count=%s | labels=%s",
        email_id,
        len(detected_intents),
        labels,
    )
    return state
