"""Seed demo contacts, list, and template for the campaign manager."""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# Project root on path (run: python scripts/seed_dashboard_demo.py from repo root)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from src.db.models import Contact, ContactList, ContactListMember, EmailTemplate
from src.db.session import get_session, initialize_database, shutdown_database


async def seed() -> None:
    await initialize_database()
    async with get_session() as db:
        existing = (await db.execute(select(EmailTemplate).limit(1))).scalar_one_or_none()
        if existing:
            print("Seed skipped — templates already exist.")
            return

        contacts = [
            Contact(
                id=uuid.uuid4(),
                email="alex.rivera@example.com",
                first_name="Alex",
                last_name="Rivera",
                company="Acme Corp",
                address="123 Market St, SF",
                custom_fields={},
            ),
            Contact(
                id=uuid.uuid4(),
                email="jordan.lee@example.com",
                first_name="Jordan",
                last_name="Lee",
                company="Bright Labs",
                address="88 King St, Toronto",
                custom_fields={},
            ),
            Contact(
                id=uuid.uuid4(),
                email="sam.patel@example.com",
                first_name="Sam",
                last_name="Patel",
                company="Northwind",
                address="45 Canal Rd, London",
                custom_fields={},
            ),
        ]
        for c in contacts:
            db.add(c)

        lst = ContactList(
            id=uuid.uuid4(),
            name="Demo outreach list",
            description="Sample contacts for campaign testing",
        )
        db.add(lst)
        await db.flush()

        for c in contacts:
            db.add(ContactListMember(id=uuid.uuid4(), list_id=lst.id, contact_id=c.id))

        tpl = EmailTemplate(
            id=uuid.uuid4(),
            name="Warm intro",
            subject="Quick note for {{first_name}} at {{company}}",
            body_html=(
                "<p>Hi {{first_name}},</p>"
                "<p>I hope this finds you well at {{company}}. "
                "I'd love to share a brief update relevant to your team.</p>"
                "<p>Best regards</p>"
            ),
            body_text="Hi {{first_name}}, hope things are well at {{company}}.",
        )
        db.add(tpl)
        await db.commit()
        print("Seeded demo contacts, list, and template.")

    await shutdown_database()


if __name__ == "__main__":
    asyncio.run(seed())
