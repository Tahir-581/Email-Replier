"""Persist intent classifier output to JSON for debugging and auditing."""

from __future__ import annotations

import json
from pathlib import Path


def _intent_logs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "intent_logs"


def save_intents_to_json(
    email_id: str,
    detected_intents: list[dict],
    email_summary: str,
    detected_concerns: list[str],
) -> None:
    """Write intent classification snapshot to ``data/intent_logs/{email_id}.json``."""
    out_dir = _intent_logs_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "email_id": email_id,
        "detected_intents": detected_intents,
        "email_summary": email_summary,
        "detected_concerns": detected_concerns,
    }
    path = out_dir / f"{email_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
