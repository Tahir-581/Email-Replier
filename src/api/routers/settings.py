"""Settings routes."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.deps import CurrentUser, DbDep
from src.api.schemas import SettingsUpdate
from src.api.settings_store import apply_runtime_overrides, get_effective_settings, set_setting

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(user: CurrentUser, db: DbDep):
    return await get_effective_settings(db)


@router.patch("")
async def patch_settings(body: SettingsUpdate, user: CurrentUser, db: DbDep):
    data = body.model_dump(exclude_unset=True)
    if "resend_api_key" in data and data["resend_api_key"] is not None:
        await set_setting(db, "resend_api_key", data["resend_api_key"], is_secret=True)
    if "form_urls" in data and data["form_urls"] is not None:
        await set_setting(db, "form_urls", data["form_urls"])
    for key in (
        "resend_from_email",
        "recruiter_name",
        "recruiter_email",
        "recruiter_title",
        "company_name",
        "company_website",
        "linkedin_url",
        "work_location",
        "send_emails_directly",
        "llm_base_url",
        "llm_model",
    ):
        if key in data and data[key] is not None:
            await set_setting(db, key, data[key])

    effective = await get_effective_settings(db)
    apply_runtime_overrides(
        {
            **{k: v for k, v in data.items() if k != "resend_api_key"},
            "resend_api_key": data.get("resend_api_key"),
        }
    )
    return effective
