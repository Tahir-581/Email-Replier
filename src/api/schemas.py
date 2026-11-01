"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class ContactCreate(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    address: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    address: str | None = None
    custom_fields: dict[str, Any] | None = None


class ContactListCreate(BaseModel):
    name: str
    description: str | None = None


class ContactListUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class AddMembersRequest(BaseModel):
    contact_ids: list[UUID]


class TemplateCreate(BaseModel):
    name: str
    subject: str = ""
    body_html: str = ""
    body_text: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    body_html: str | None = None
    body_text: str | None = None


class TemplatePreviewRequest(BaseModel):
    subject: str
    body_html: str
    contact_id: UUID | None = None
    sample: dict[str, Any] | None = None


class CampaignCreate(BaseModel):
    name: str
    list_id: UUID | None = None
    template_id: UUID | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    list_id: UUID | None = None
    template_id: UUID | None = None


class ReplyUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None


class SendReplyRequest(BaseModel):
    force_send: bool = False


class PipelineRunRequest(BaseModel):
    skip_pull: bool = True
    limit: int | None = None


class PolicyConfigUpdate(BaseModel):
    form_urls: dict[str, str] | None = None
    send_emails_directly: bool | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    recruiter_title: str | None = None
    company_name: str | None = None
    company_website: str | None = None
    linkedin_url: str | None = None
    work_location: str | None = None


class SettingsUpdate(BaseModel):
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    recruiter_name: str | None = None
    recruiter_email: str | None = None
    recruiter_title: str | None = None
    company_name: str | None = None
    company_website: str | None = None
    linkedin_url: str | None = None
    work_location: str | None = None
    send_emails_directly: bool | None = None
    form_urls: dict[str, str] | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
