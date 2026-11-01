"""Contacts and lists routes."""

from __future__ import annotations

import csv
import io
import uuid
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select

from src.api.deps import CurrentUser, DbDep
from src.api.schemas import AddMembersRequest, ContactCreate, ContactListCreate, ContactListUpdate, ContactUpdate
from src.db.models import Contact, ContactList, ContactListMember

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("")
async def list_contacts(
    user: CurrentUser,
    db: DbDep,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(Contact).order_by(Contact.created_at.desc())
    count_q = select(func.count()).select_from(Contact)
    if q:
        like = f"%{q}%"
        filt = (
            Contact.email.ilike(like)
            | Contact.first_name.ilike(like)
            | Contact.last_name.ilike(like)
            | Contact.company.ilike(like)
        )
        query = query.where(filt)
        count_q = count_q.where(filt)
    total = (await db.execute(count_q)).scalar() or 0
    rows = (await db.execute(query.offset(offset).limit(limit))).scalars().all()
    return {"total": total, "items": [c.to_dict() for c in rows]}


@router.post("")
async def create_contact(body: ContactCreate, user: CurrentUser, db: DbDep):
    contact = Contact(
        id=uuid.uuid4(),
        email=str(body.email).lower(),
        first_name=body.first_name,
        last_name=body.last_name,
        company=body.company,
        address=body.address,
        custom_fields=body.custom_fields or {},
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact.to_dict()


@router.post("/import")
async def import_contacts(user: CurrentUser, db: DbDep, file: UploadFile = File(...)):
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    created = 0
    skipped = 0
    for row in reader:
        email = (row.get("email") or row.get("Email") or "").strip().lower()
        if not email:
            skipped += 1
            continue
        existing = (
            await db.execute(select(Contact).where(Contact.email == email))
        ).scalar_one_or_none()
        if existing:
            skipped += 1
            continue
        contact = Contact(
            id=uuid.uuid4(),
            email=email,
            first_name=(row.get("first_name") or row.get("First Name") or "").strip() or None,
            last_name=(row.get("last_name") or row.get("Last Name") or "").strip() or None,
            company=(row.get("company") or row.get("Company") or "").strip() or None,
            address=(row.get("address") or row.get("Address") or "").strip() or None,
            custom_fields={},
        )
        db.add(contact)
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped}


@router.get("/export/csv")
async def export_contacts(user: CurrentUser, db: DbDep):
    rows = (await db.execute(select(Contact).order_by(Contact.created_at.desc()))).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "first_name", "last_name", "company", "address"])
    for c in rows:
        writer.writerow([c.email, c.first_name or "", c.last_name or "", c.company or "", c.address or ""])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts_export.csv"},
    )


@router.get("/{contact_id}")
async def get_contact(contact_id: UUID, user: CurrentUser, db: DbDep):
    contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact.to_dict()


@router.patch("/{contact_id}")
async def update_contact(contact_id: UUID, body: ContactUpdate, user: CurrentUser, db: DbDep):
    contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).lower()
    for k, v in data.items():
        setattr(contact, k, v)
    await db.commit()
    await db.refresh(contact)
    return contact.to_dict()


@router.delete("/{contact_id}")
async def delete_contact(contact_id: UUID, user: CurrentUser, db: DbDep):
    contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.execute(delete(ContactListMember).where(ContactListMember.contact_id == contact_id))
    await db.delete(contact)
    await db.commit()
    return {"ok": True}


# --- Lists ---

lists_router = APIRouter(prefix="/lists", tags=["lists"])


@lists_router.get("")
async def list_lists(user: CurrentUser, db: DbDep):
    rows = (await db.execute(select(ContactList).order_by(ContactList.created_at.desc()))).scalars().all()
    items = []
    for lst in rows:
        count = (
            await db.execute(
                select(func.count()).select_from(ContactListMember).where(ContactListMember.list_id == lst.id)
            )
        ).scalar() or 0
        d = lst.to_dict()
        d["member_count"] = count
        items.append(d)
    return {"items": items}


@lists_router.post("")
async def create_list(body: ContactListCreate, user: CurrentUser, db: DbDep):
    lst = ContactList(id=uuid.uuid4(), name=body.name, description=body.description)
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    d = lst.to_dict()
    d["member_count"] = 0
    return d


@lists_router.patch("/{list_id}")
async def update_list(list_id: UUID, body: ContactListUpdate, user: CurrentUser, db: DbDep):
    lst = (await db.execute(select(ContactList).where(ContactList.id == list_id))).scalar_one_or_none()
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(lst, k, v)
    await db.commit()
    await db.refresh(lst)
    return lst.to_dict()


@lists_router.delete("/{list_id}")
async def delete_list(list_id: UUID, user: CurrentUser, db: DbDep):
    lst = (await db.execute(select(ContactList).where(ContactList.id == list_id))).scalar_one_or_none()
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    await db.execute(delete(ContactListMember).where(ContactListMember.list_id == list_id))
    await db.delete(lst)
    await db.commit()
    return {"ok": True}


@lists_router.get("/{list_id}/members")
async def list_members(list_id: UUID, user: CurrentUser, db: DbDep):
    member_ids = (
        await db.execute(select(ContactListMember.contact_id).where(ContactListMember.list_id == list_id))
    ).scalars().all()
    if not member_ids:
        return {"items": []}
    contacts = (
        await db.execute(select(Contact).where(Contact.id.in_(member_ids)))
    ).scalars().all()
    return {"items": [c.to_dict() for c in contacts]}


@lists_router.post("/{list_id}/members")
async def add_members(list_id: UUID, body: AddMembersRequest, user: CurrentUser, db: DbDep):
    lst = (await db.execute(select(ContactList).where(ContactList.id == list_id))).scalar_one_or_none()
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    added = 0
    for cid in body.contact_ids:
        existing = (
            await db.execute(
                select(ContactListMember).where(
                    ContactListMember.list_id == list_id,
                    ContactListMember.contact_id == cid,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        db.add(ContactListMember(id=uuid.uuid4(), list_id=list_id, contact_id=cid))
        added += 1
    await db.commit()
    return {"added": added}
