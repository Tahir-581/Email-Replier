"""HR recruitment inbox / pipeline / rules routes."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from src.api.deps import CurrentUser, DbDep
from src.api.schemas import PipelineRunRequest, PolicyConfigUpdate, ReplyUpdate, SendReplyRequest
from src.api.settings_store import apply_runtime_overrides, get_effective_settings, set_setting
from src.db.models import Email, Reply
from src.utils.config import INTENT_BUCKETS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hr", tags=["hr"])


@router.get("/emails")
async def list_emails(
    user: CurrentUser,
    db: DbDep,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Email).order_by(Email.created_at.desc())
    count_q = select(func.count()).select_from(Email)
    if status:
        query = query.where(Email.status == status)
        count_q = count_q.where(Email.status == status)
    if q:
        like = f"%{q}%"
        filt = (Email.subject.ilike(like)) | (Email.from_addr.ilike(like)) | (Email.body.ilike(like))
        query = query.where(filt)
        count_q = count_q.where(filt)
    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(query.offset(offset).limit(limit))).scalars().all()
    return {"total": total, "items": [e.to_dict() for e in rows]}


@router.get("/emails/{email_id}")
async def get_email(email_id: str, user: CurrentUser, db: DbDep):
    result = await db.execute(select(Email).where(Email.email_id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        # try UUID pk
        try:
            uid = UUID(email_id)
            result = await db.execute(select(Email).where(Email.id == uid))
            email = result.scalar_one_or_none()
        except ValueError:
            email = None
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    replies = (
        await db.execute(
            select(Reply).where(Reply.email_id == email.email_id).order_by(Reply.created_at.desc())
        )
    ).scalars().all()
    return {
        "email": email.to_dict(),
        "replies": [r.to_dict() for r in replies],
    }


@router.patch("/replies/{reply_id}")
async def update_reply(reply_id: UUID, body: ReplyUpdate, user: CurrentUser, db: DbDep):
    result = await db.execute(select(Reply).where(Reply.id == reply_id))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    if body.subject is not None:
        reply.subject = body.subject
    if body.body is not None:
        reply.body = body.body
    await db.commit()
    await db.refresh(reply)
    return reply.to_dict()


@router.post("/replies/{reply_id}/send")
async def send_reply(
    reply_id: UUID,
    body: SendReplyRequest,
    user: CurrentUser,
    db: DbDep,
):
    result = await db.execute(select(Reply).where(Reply.id == reply_id))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    if not reply.to_addr or not reply.body:
        raise HTTPException(status_code=400, detail="Reply missing recipient or body")

    effective = await get_effective_settings(db)
    apply_runtime_overrides(effective)
    force_send = body.force_send or bool(effective.get("send_emails_directly"))

    try:
        from src.agents.email_sender import (
            _create_draft_via_gmail_oauth,
            _send_email_via_gmail_oauth,
            _text_to_simple_html,
        )

        html_body = _text_to_simple_html(reply.body or "")
        if force_send:
            _send_email_via_gmail_oauth(
                to_addr=reply.to_addr,
                subject=reply.subject or "",
                body=reply.body or "",
                html_body=html_body,
            )
        else:
            email_row = (
                await db.execute(select(Email).where(Email.email_id == reply.email_id))
            ).scalar_one_or_none()
            _create_draft_via_gmail_oauth(
                to_addr=reply.to_addr,
                subject=reply.subject or "",
                body=reply.body or "",
                html_body=html_body,
                thread_id=(email_row.thread_id if email_row else None) or reply.thread_id,
            )
        reply.sent_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as exc:
        logger.exception("Failed to send/draft reply")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": True,
        "mode": "sent" if force_send else "draft",
        "reply": reply.to_dict(),
    }


@router.post("/emails/{email_id}/reprocess")
async def reprocess_email(
    email_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbDep,
):
    result = await db.execute(select(Email).where(Email.email_id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    email.status = "pending"
    await db.commit()

    def _run():
        try:
            from src.db.session import get_pending_emails
            from src.pipeline.batch import process_email_batch

            pending = [e for e in get_pending_emails() if e.get("email_id") == email_id]
            if not pending:
                pending = get_pending_emails()[:1]
            process_email_batch(pending)
        except Exception:
            logger.exception("Reprocess failed for %s", email_id)

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Reprocess queued"}


def _run_pipeline_job(skip_pull: bool, limit: int | None) -> None:
    try:
        if not skip_pull:
            try:
                import asyncio

                from scripts.run_pipeline import run_ingestion

                asyncio.run(run_ingestion(limit=limit or 50))
            except Exception:
                logger.warning("Ingestion step skipped/failed", exc_info=True)
        from src.db.session import get_pending_emails
        from src.pipeline.batch import process_email_batch

        emails = get_pending_emails()
        if limit is not None:
            emails = emails[: max(0, int(limit))]
        process_email_batch(emails)
    except Exception:
        logger.exception("Pipeline run failed")


@router.post("/pipeline/run")
async def run_pipeline(
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
):
    background_tasks.add_task(_run_pipeline_job, body.skip_pull, body.limit)
    return {"ok": True, "message": "Pipeline started"}


@router.get("/pipeline/stats")
async def pipeline_stats(user: CurrentUser, db: DbDep):
    async def _count(status: str | None = None) -> int:
        q = select(func.count()).select_from(Email)
        if status:
            q = q.where(Email.status == status)
        return (await db.execute(q)).scalar() or 0

    return {
        "pending": await _count("pending"),
        "processing": await _count("processing"),
        "processed": await _count("processed"),
        "irrelevant": await _count("irrelevant"),
        "error": await _count("error"),
        "total": await _count(),
        "replies": (await db.execute(select(func.count()).select_from(Reply))).scalar() or 0,
    }


@router.get("/intents")
async def list_intents(user: CurrentUser):
    return [{"id": k, "label": v} for k, v in INTENT_BUCKETS.items()]


@router.get("/rules")
async def get_rules(user: CurrentUser, db: DbDep):
    effective = await get_effective_settings(db)
    return {
        "form_urls": effective["form_urls"],
        "send_emails_directly": effective["send_emails_directly"],
        "recruiter_name": effective["recruiter_name"],
        "recruiter_email": effective["recruiter_email"],
        "recruiter_title": effective["recruiter_title"],
        "company_name": effective["company_name"],
        "company_website": effective["company_website"],
        "linkedin_url": effective["linkedin_url"],
        "work_location": effective["work_location"],
        "intents": [{"id": k, "label": v} for k, v in INTENT_BUCKETS.items()],
        "notes": (
            "LLM policy prompts remain code-owned. Dashboard edits operational knobs "
            "(forms, branding, send mode)."
        ),
    }


@router.put("/rules")
async def update_rules(body: PolicyConfigUpdate, user: CurrentUser, db: DbDep):
    payload = body.model_dump(exclude_unset=True)
    if "form_urls" in payload and payload["form_urls"] is not None:
        await set_setting(db, "form_urls", payload["form_urls"])
    for key in (
        "send_emails_directly",
        "recruiter_name",
        "recruiter_email",
        "recruiter_title",
        "company_name",
        "company_website",
        "linkedin_url",
        "work_location",
    ):
        if key in payload and payload[key] is not None:
            await set_setting(db, key, payload[key])
    effective = await get_effective_settings(db)
    apply_runtime_overrides(effective)
    return await get_rules(user, db)


@router.get("/export/replies")
async def export_replies(user: CurrentUser, db: DbDep):
    rows = (await db.execute(select(Reply).order_by(Reply.created_at.desc()))).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "email_id",
            "to_addr",
            "from_addr",
            "subject",
            "intent_label",
            "profile_type",
            "sent_at",
            "created_at",
            "body",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                str(r.id),
                r.email_id,
                r.to_addr,
                r.from_addr,
                r.subject,
                r.intent_label,
                r.profile_type,
                r.sent_at.isoformat() if r.sent_at else "",
                r.created_at.isoformat() if r.created_at else "",
                r.body,
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=replies_export.csv"},
    )
