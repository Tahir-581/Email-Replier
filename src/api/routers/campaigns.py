"""Campaign routes."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import delete, func, select

from src.api.deps import CurrentUser, DbDep
from src.api.schemas import CampaignCreate, CampaignUpdate
from src.api.settings_store import get_setting
from src.campaigns import contact_merge_context, render_merge_tags, resolve_resend_credentials, send_via_resend
from src.db.models import Campaign, CampaignMessage, Contact, ContactListMember, EmailTemplate
from src.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("")
async def list_campaigns(user: CurrentUser, db: DbDep):
    rows = (await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))).scalars().all()
    items = []
    for c in rows:
        d = c.to_dict()
        msg_count = (
            await db.execute(
                select(func.count()).select_from(CampaignMessage).where(CampaignMessage.campaign_id == c.id)
            )
        ).scalar() or 0
        sent_count = (
            await db.execute(
                select(func.count())
                .select_from(CampaignMessage)
                .where(CampaignMessage.campaign_id == c.id, CampaignMessage.status == "sent")
            )
        ).scalar() or 0
        d["message_count"] = msg_count
        d["sent_count"] = sent_count
        items.append(d)
    return {"items": items}


@router.post("")
async def create_campaign(body: CampaignCreate, user: CurrentUser, db: DbDep):
    campaign = Campaign(
        id=uuid.uuid4(),
        name=body.name,
        list_id=body.list_id,
        template_id=body.template_id,
        status="draft",
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign.to_dict()


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: UUID, user: CurrentUser, db: DbDep):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    messages = (
        await db.execute(
            select(CampaignMessage)
            .where(CampaignMessage.campaign_id == campaign_id)
            .order_by(CampaignMessage.created_at.desc())
            .limit(200)
        )
    ).scalars().all()
    return {
        "campaign": campaign.to_dict(),
        "messages": [m.to_dict() for m in messages],
    }


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: UUID, body: CampaignUpdate, user: CurrentUser, db: DbDep):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status == "sending":
        raise HTTPException(status_code=400, detail="Cannot edit a campaign that is sending")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(campaign, k, v)
    await db.commit()
    await db.refresh(campaign)
    return campaign.to_dict()


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: UUID, user: CurrentUser, db: DbDep):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.execute(delete(CampaignMessage).where(CampaignMessage.campaign_id == campaign_id))
    await db.delete(campaign)
    await db.commit()
    return {"ok": True}


@router.get("/{campaign_id}/preview")
async def preview_campaign(campaign_id: UUID, user: CurrentUser, db: DbDep):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign or not campaign.template_id or not campaign.list_id:
        raise HTTPException(status_code=400, detail="Campaign needs list and template")
    tpl = (
        await db.execute(select(EmailTemplate).where(EmailTemplate.id == campaign.template_id))
    ).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    member_ids = (
        await db.execute(
            select(ContactListMember.contact_id).where(ContactListMember.list_id == campaign.list_id)
        )
    ).scalars().all()
    contacts = []
    if member_ids:
        contacts = (
            await db.execute(select(Contact).where(Contact.id.in_(member_ids)).limit(5))
        ).scalars().all()
    previews = []
    for c in contacts:
        ctx = contact_merge_context(c.to_dict())
        previews.append(
            {
                "to_email": c.email,
                "subject": render_merge_tags(tpl.subject, ctx),
                "body_html": render_merge_tags(tpl.body_html, ctx),
            }
        )
    return {"previews": previews, "recipient_count": len(member_ids)}


async def _send_campaign_job(campaign_id: UUID) -> None:
    async with get_session() as db:
        campaign = (
            await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        ).scalar_one_or_none()
        if not campaign:
            return
        try:
            if not campaign.list_id or not campaign.template_id:
                raise RuntimeError("Campaign missing list or template")
            tpl = (
                await db.execute(select(EmailTemplate).where(EmailTemplate.id == campaign.template_id))
            ).scalar_one_or_none()
            if not tpl:
                raise RuntimeError("Template not found")

            stored_key = await get_setting(db, "resend_api_key")
            stored_from = await get_setting(db, "resend_from_email")
            api_key, from_email = resolve_resend_credentials(
                stored_key if isinstance(stored_key, str) else None,
                stored_from if isinstance(stored_from, str) else None,
            )

            member_ids = (
                await db.execute(
                    select(ContactListMember.contact_id).where(
                        ContactListMember.list_id == campaign.list_id
                    )
                )
            ).scalars().all()
            contacts = []
            if member_ids:
                contacts = (
                    await db.execute(select(Contact).where(Contact.id.in_(member_ids)))
                ).scalars().all()

            # Clear previous pending messages for re-send of draft
            await db.execute(delete(CampaignMessage).where(CampaignMessage.campaign_id == campaign_id))

            sent_ok = 0
            for contact in contacts:
                ctx = contact_merge_context(contact.to_dict())
                subject = render_merge_tags(tpl.subject, ctx)
                html = render_merge_tags(tpl.body_html, ctx)
                text = render_merge_tags(tpl.body_text or "", ctx) if tpl.body_text else None
                msg = CampaignMessage(
                    id=uuid.uuid4(),
                    campaign_id=campaign_id,
                    contact_id=contact.id,
                    to_email=contact.email,
                    subject=subject,
                    body_html=html,
                    status="pending",
                )
                db.add(msg)
                await db.flush()
                try:
                    provider_id = await send_via_resend(
                        api_key=api_key,
                        from_email=from_email,
                        to_email=contact.email,
                        subject=subject,
                        html=html,
                        text=text,
                    )
                    msg.status = "sent"
                    msg.provider_id = provider_id
                    msg.sent_at = datetime.now(timezone.utc)
                    sent_ok += 1
                except Exception as exc:
                    msg.status = "failed"
                    msg.error = str(exc)
                    logger.exception("Campaign message failed for %s", contact.email)

            if not contacts:
                campaign.status = "failed"
                campaign.error = "No contacts in list"
            elif sent_ok == 0:
                campaign.status = "failed"
                campaign.error = "All messages failed"
            else:
                campaign.status = "sent"
                campaign.error = None
            campaign.sent_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            campaign.status = "failed"
            campaign.error = str(exc)
            await db.commit()
            logger.exception("Campaign send failed")


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbDep,
):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status == "sending":
        raise HTTPException(status_code=400, detail="Already sending")
    if not campaign.list_id or not campaign.template_id:
        raise HTTPException(status_code=400, detail="Assign a list and template first")

    campaign.status = "sending"
    campaign.error = None
    await db.commit()

    background_tasks.add_task(_send_campaign_job, campaign_id)
    return {"ok": True, "message": "Campaign send started"}
