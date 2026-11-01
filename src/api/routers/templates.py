"""Email templates routes."""

from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from src.api.deps import CurrentUser, DbDep
from src.api.schemas import TemplateCreate, TemplatePreviewRequest, TemplateUpdate
from src.campaigns import contact_merge_context, render_merge_tags
from src.db.models import Contact, EmailTemplate

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
async def list_templates(user: CurrentUser, db: DbDep):
    rows = (
        await db.execute(select(EmailTemplate).order_by(EmailTemplate.created_at.desc()))
    ).scalars().all()
    return {"items": [t.to_dict() for t in rows]}


@router.post("")
async def create_template(body: TemplateCreate, user: CurrentUser, db: DbDep):
    tpl = EmailTemplate(
        id=uuid.uuid4(),
        name=body.name,
        subject=body.subject,
        body_html=body.body_html,
        body_text=body.body_text,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl.to_dict()


@router.get("/{template_id}")
async def get_template(template_id: UUID, user: CurrentUser, db: DbDep):
    tpl = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl.to_dict()


@router.patch("/{template_id}")
async def update_template(template_id: UUID, body: TemplateUpdate, user: CurrentUser, db: DbDep):
    tpl = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(tpl, k, v)
    await db.commit()
    await db.refresh(tpl)
    return tpl.to_dict()


@router.delete("/{template_id}")
async def delete_template(template_id: UUID, user: CurrentUser, db: DbDep):
    tpl = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(tpl)
    await db.commit()
    return {"ok": True}


@router.post("/preview")
async def preview_template(body: TemplatePreviewRequest, user: CurrentUser, db: DbDep):
    contact_dict = body.sample
    if body.contact_id:
        contact = (
            await db.execute(select(Contact).where(Contact.id == body.contact_id))
        ).scalar_one_or_none()
        if contact:
            contact_dict = contact.to_dict()
    if not contact_dict:
        contact_dict = {
            "first_name": "Alex",
            "last_name": "Rivera",
            "email": "alex@example.com",
            "company": "Acme Corp",
            "address": "123 Market St",
            "custom_fields": {},
        }
    ctx = contact_merge_context(contact_dict)
    return {
        "subject": render_merge_tags(body.subject, ctx),
        "body_html": render_merge_tags(body.body_html, ctx),
        "context": ctx,
    }
