"""Campaign merge-tag rendering and Resend sending."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from src.utils.config import settings

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def contact_merge_context(contact: dict[str, Any] | None) -> dict[str, str]:
    contact = contact or {}
    first = str(contact.get("first_name") or "")
    last = str(contact.get("last_name") or "")
    full = f"{first} {last}".strip()
    ctx: dict[str, str] = {
        "first_name": first,
        "last_name": last,
        "full_name": full or str(contact.get("email") or ""),
        "email": str(contact.get("email") or ""),
        "company": str(contact.get("company") or ""),
        "address": str(contact.get("address") or ""),
    }
    custom = contact.get("custom_fields") or {}
    if isinstance(custom, dict):
        for key, value in custom.items():
            ctx[str(key)] = "" if value is None else str(value)
    return ctx


def render_merge_tags(template: str, context: dict[str, str]) -> str:
    if not template:
        return ""

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return _TAG_RE.sub(_repl, template)


async def send_via_resend(
    *,
    api_key: str,
    from_email: str,
    to_email: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> str:
    """Send one email via Resend. Returns provider message id."""
    if not api_key:
        raise RuntimeError("Resend API key is not configured")
    if not from_email:
        raise RuntimeError("Resend from email is not configured")

    payload: dict[str, Any] = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            detail = resp.text
            logger.error("Resend send failed: %s %s", resp.status_code, detail)
            raise RuntimeError(f"Resend error {resp.status_code}: {detail}")
        data = resp.json()
        return str(data.get("id") or "")


def resolve_resend_credentials(
    stored_api_key: str | None = None,
    stored_from: str | None = None,
) -> tuple[str, str]:
    api_key = (stored_api_key or settings.RESEND_API_KEY or "").strip()
    from_email = (stored_from or settings.RESEND_FROM_EMAIL or settings.RECRUITER_EMAIL or "").strip()
    return api_key, from_email
