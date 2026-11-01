"""Settings store helpers (DB-backed overrides + secret encryption)."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AppSetting
from src.utils.config import FORM_URLS, settings


def _fernet() -> Fernet:
    raw = (settings.SETTINGS_FERNET_KEY or settings.JWT_SECRET_KEY or "dev-key").encode()
    digest = hashlib.sha256(raw).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""


async def get_setting(db: AsyncSession, key: str) -> Any | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if not row:
        return None
    value = row.value
    if row.is_secret and isinstance(value, dict) and "cipher" in value:
        return decrypt_secret(value["cipher"])
    return value


async def set_setting(
    db: AsyncSession,
    key: str,
    value: Any,
    *,
    is_secret: bool = False,
) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    store_value: Any
    if is_secret:
        plain = "" if value is None else str(value)
        store_value = {"cipher": encrypt_secret(plain)} if plain else {"cipher": ""}
    else:
        store_value = value

    if row:
        row.value = store_value
        row.is_secret = is_secret
    else:
        import uuid

        db.add(
            AppSetting(
                id=uuid.uuid4(),
                key=key,
                value=store_value,
                is_secret=is_secret,
            )
        )
    await db.commit()


async def get_effective_settings(db: AsyncSession) -> dict[str, Any]:
    """Merge env defaults with DB overrides for the Settings UI."""
    form_urls = dict(FORM_URLS)
    stored_forms = await get_setting(db, "form_urls")
    if isinstance(stored_forms, dict):
        form_urls.update({str(k): str(v) for k, v in stored_forms.items()})

    resend_key = await get_setting(db, "resend_api_key")
    if not resend_key:
        resend_key = settings.RESEND_API_KEY or ""

    async def _str(key: str, default: str) -> str:
        val = await get_setting(db, key)
        return str(val) if val is not None and val != "" else default

    async def _bool(key: str, default: bool) -> bool:
        val = await get_setting(db, key)
        if val is None:
            return default
        return bool(val)

    gmail_token_path = settings.GMAIL_TOKEN_FILE
    gmail_connected = False
    try:
        from pathlib import Path

        path = Path(gmail_token_path)
        if not path.is_absolute():
            from src.utils.config import PROJECT_ROOT

            path = PROJECT_ROOT / path
        gmail_connected = path.exists() and path.stat().st_size > 0
    except Exception:
        gmail_connected = False

    return {
        "resend_api_key_set": bool(resend_key),
        "resend_from_email": await _str("resend_from_email", settings.RESEND_FROM_EMAIL or settings.RECRUITER_EMAIL or ""),
        "recruiter_name": await _str("recruiter_name", settings.RECRUITER_NAME),
        "recruiter_email": await _str("recruiter_email", settings.RECRUITER_EMAIL),
        "recruiter_title": await _str("recruiter_title", settings.RECRUITER_TITLE),
        "company_name": await _str("company_name", settings.COMPANY_NAME),
        "company_website": await _str("company_website", settings.COMPANY_WEBSITE),
        "linkedin_url": await _str("linkedin_url", settings.LINKEDIN_URL),
        "work_location": await _str("work_location", settings.WORK_LOCATION),
        "send_emails_directly": await _bool("send_emails_directly", settings.SEND_EMAILS_DIRECTLY),
        "form_urls": form_urls,
        "llm_base_url": await _str("llm_base_url", settings.LLM_BASE_URL),
        "llm_model": await _str("llm_model", settings.LLM_MODEL),
        "gmail_connected": gmail_connected,
        "gmail_token_file": settings.GMAIL_TOKEN_FILE,
    }


def apply_runtime_overrides(data: dict[str, Any]) -> None:
    """Best-effort in-process overrides for modules that import module-level constants."""
    import src.utils.config as cfg

    mapping = {
        "recruiter_name": "RECRUITER_NAME",
        "recruiter_email": "RECRUITER_EMAIL",
        "recruiter_title": "RECRUITER_TITLE",
        "company_name": "COMPANY_NAME",
        "company_website": "COMPANY_WEBSITE",
        "linkedin_url": "LINKEDIN_URL",
        "work_location": "WORK_LOCATION",
        "send_emails_directly": "SEND_EMAILS_DIRECTLY",
        "llm_base_url": "LLM_BASE_URL",
        "llm_model": "LLM_MODEL",
        "resend_api_key": "RESEND_API_KEY",
        "resend_from_email": "RESEND_FROM_EMAIL",
    }
    for src_key, attr in mapping.items():
        if src_key in data and data[src_key] is not None:
            setattr(cfg.settings, attr, data[src_key])
            if hasattr(cfg, attr):
                setattr(cfg, attr, data[src_key])

    if "form_urls" in data and isinstance(data["form_urls"], dict):
        cfg.FORM_URLS.update(data["form_urls"])
