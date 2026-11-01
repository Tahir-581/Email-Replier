"""
Database session management — merged version.

Contains:
1. Collaborator's async engine + session setup (PostgreSQL via asyncpg)
2. Our sync pipeline functions that bridge into the async layer

Bridge pattern:
  Our LangGraph pipeline is synchronous.
  The DB session is async (asyncpg + SQLAlchemy async).
  Every DB call is wrapped with _run() to execute async code from sync context.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import asyncpg
import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.db.models import Email, Log, Reply
from src.utils.config import settings

# ── Loggers ───────────────────────────────────────────────────────────────────
struct_logger = structlog.get_logger(__name__)
logger = logging.getLogger(__name__)

# ── Global engine and session maker ──────────────────────────────────────────
engine = None
session_maker = None


def _ensure_windows_selector_event_loop() -> None:
    """
    Psycopg3 async is incompatible with Windows' default ProactorEventLoop.
    Force SelectorEventLoop policy on Windows before any asyncio.run() usage.
    """
    if sys.platform != "win32":
        return

    policy = asyncio.get_event_loop_policy()
    # Only Windows has these policy classes; guard with getattr.
    windows_selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if windows_selector_policy is None:
        return

    if not isinstance(policy, windows_selector_policy):
        asyncio.set_event_loop_policy(windows_selector_policy())


# =============================================================================
# SECTION 1 — Collaborator's async DB setup (do NOT modify)
# =============================================================================

async def initialize_database() -> None:
    """Initialize database engine and session maker."""
    global engine, session_maker

    try:
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            poolclass=NullPool,
            future=True,
        )

        session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            # Keep schema aligned with Reply model (safe when column already exists).
            await conn.execute(
                text(
                    "ALTER TABLE replies ADD COLUMN IF NOT EXISTS detected_intents JSONB"
                )
            )

        struct_logger.info("Database initialized successfully")

    except Exception as e:
        struct_logger.error(f"Failed to initialize database: {e}")
        raise


async def close_database() -> None:
    """Close database engine."""
    global engine
    if engine:
        await engine.dispose()
        struct_logger.info("Database connection closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session context manager."""
    if not session_maker:
        await initialize_database()

    async with session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            struct_logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def create_database_if_not_exists() -> None:
    """Create database if it doesn't exist."""
    try:
        db_url = settings.DATABASE_BASE_URL
        if not db_url:
            raise ValueError("DATABASE_BASE_URL not configured")
        
        # Connect to PostgreSQL server (without database)
        conn = await asyncpg.connect(db_url)
        db_name = settings.EMAIL_DB

        result = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )

        if not result:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            struct_logger.info(f"Database '{db_name}' created successfully")
        else:
            struct_logger.info(f"Database '{db_name}' already exists")

        await conn.close()

    except Exception as e:
        struct_logger.error(f"Failed to create database: {e}")
        raise


async def test_database_connection() -> bool:
    """Test database connection."""
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        struct_logger.info("Database connection test successful")
        return True
    except Exception as e:
        struct_logger.error(f"Database connection test failed: {e}")
        return False


async def startup_database() -> None:
    """Initialize database on application startup."""
    try:
        await create_database_if_not_exists()
        await initialize_database()
        await test_database_connection()
    except Exception as e:
        struct_logger.error(f"Database startup failed: {e}")
        raise


async def shutdown_database() -> None:
    """Cleanup database on application shutdown."""
    await close_database()


# =============================================================================
# SECTION 2 — Our sync pipeline functions
# =============================================================================

# ─── Async → Sync bridge ─────────────────────────────────────────────────────

def _run(coro):
    """
    Run an async coroutine synchronously.
    Required because our LangGraph pipeline is sync
    but the DB session is async.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _ensure_windows_selector_event_loop()
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            _ensure_windows_selector_event_loop()
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - bridge safety
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


# ─── DB row → our EmailState dict ────────────────────────────────────────────

def _email_to_state(email: Email) -> dict:
    """
    Convert a DB Email row into our pipeline EmailState dict.

    Differences handled:
      - DB column 'date' → state field 'received_at'
    """
    return {
        "id":          str(email.id),
        "email_id":    email.email_id,
        "message_id":  email.message_id or "",
        "thread_id":   email.thread_id or email.email_id,
        "subject":     email.subject or "",
        "from_addr":   email.from_addr or "",
        "to_addr":     email.to_addr or "",
        "body":        email.body or "",
        "date":        email.date,
        "received_at": email.date.isoformat() if email.date else _now(),
        "status":      email.status or "pending",
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Emails ───────────────────────────────────────────────────────────────────

def get_pending_emails() -> list[dict]:
    """
    Fetch all emails with status='pending' from PostgreSQL.
    Returns list of dicts matching our EmailState schema.
    """
    async def _fetch():
        async with get_session() as session:
            result = await session.execute(
                select(Email).where(Email.status == "pending")
            )
            emails = result.scalars().all()
            return [_email_to_state(e) for e in emails]

    try:
        return _run(_fetch())
    except Exception as e:
        logger.error(f"[session] get_pending_emails failed: {e}")
        return []


def update_email_status(email_id: str, status: str) -> None:
    """
    Update email status in PostgreSQL by email_id.

    Status values we write:
      'processed'  → email fully handled, reply sent
      'irrelevant' → email not relevant to recruiting
      'error'      → pipeline failed for this email
    """
    async def _update():
        async with get_session() as session:
            await session.execute(
                update(Email)
                .where(Email.email_id == email_id)
                .values(
                    status=status,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            await session.commit()

    try:
        _run(_update())
        logger.debug(f"[session] email_id={email_id} → status={status}")
    except Exception as e:
        logger.error(f"[session] update_email_status failed: {e}")


def save_email(email_data: dict) -> None:
    """
    Save a new email to PostgreSQL.
    Called when pulling emails from Gmail.
    Skips if email already exists.
    """
    async def _save():
        async with get_session() as session:
            email_id = email_data.get("id")
            if not email_id:
                return False

            # Check if email already exists
            existing = await session.execute(
                select(Email).where(Email.email_id == email_id)
            )
            if existing.scalar_one_or_none():
                return False  # Skip duplicate

            # Parse from address
            from_raw = email_data.get("from", "")
            from_addr = from_raw
            if "<" in from_raw and ">" in from_raw:
                from_addr = from_raw.split("<")[1].split(">")[0]

            # Parse date
            date_str = email_data.get("date", "")
            email_date = None
            try:
                from email.utils import parsedate_to_datetime
                email_date = parsedate_to_datetime(date_str)
            except Exception:
                email_date = datetime.now(timezone.utc)

            email = Email(
                email_id=email_id,
                message_id=email_id,
                thread_id=email_data.get("thread_id"),
                subject=email_data.get("subject", ""),
                from_addr=from_addr,
                to_addr=email_data.get("to", ""),
                date=email_date,
                body=email_data.get("body", ""),
                status="pending",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(email)
            await session.commit()
            return True

    try:
        saved = _run(_save())
        if saved:
            logger.info(f"[session] Email saved: {email_data.get('id')}")
    except Exception as e:
        logger.warning(f"[session] save_email skipped/failed: {e}")


# ─── History ──────────────────────────────────────────────────────────────────

def get_history(email_id: str) -> list[dict]:
    """
    Read thread history from the Email row's 'history' JSON column.
    The history is stored directly on the email record.
    """
    async def _fetch():
        async with get_session() as session:
            result = await session.execute(
                select(Email).where(Email.email_id == email_id)
            )
            email = result.scalar_one_or_none()
            if email and email.history:
                if isinstance(email.history, list):
                    return email.history
            return []

    try:
        return _run(_fetch())
    except Exception as e:
        logger.error(f"[session] get_history failed: {e}")
        return []


def save_history(record: dict) -> None:
    """
    Append a history record to the Email row's 'history' JSON column.
    """
    async def _save():
        async with get_session() as session:
            result = await session.execute(
                select(Email).where(Email.email_id == record.get("email_id"))
            )
            email = result.scalar_one_or_none()
            if email:
                current = email.history if isinstance(email.history, list) else []
                current.append(record)
                email.history = current
                await session.commit()

    try:
        _run(_save())
    except Exception as e:
        logger.error(f"[session] save_history failed: {e}")


# ─── Replies ──────────────────────────────────────────────────────────────────

def save_reply(reply: dict) -> None:
    """Save reply to PostgreSQL replies table."""
    async def _save():
        async with get_session() as session:
            sent_at_val = None
            if reply.get("sent_at"):
                try:
                    sent_at_val = datetime.fromisoformat(reply["sent_at"])
                except Exception:
                    sent_at_val = None

            di = reply.get("detected_intents")
            if di is not None and not isinstance(di, list):
                di = None

            record = Reply(
                id=uuid.uuid4(),
                email_id=reply.get("email_id", ""),
                thread_id=reply.get("thread_id", ""),
                from_addr=reply.get("from_addr", ""),
                to_addr=reply.get("to_addr", ""),
                subject=reply.get("subject", ""),
                body=reply.get("body", ""),
                intent_label=reply.get("intent_label", ""),
                profile_type=reply.get("profile_type", ""),
                sender_name=reply.get("sender_name", ""),
                detected_intents=di,
                sent_at=sent_at_val,
            )
            session.add(record)
            await session.commit()

    try:
        _run(_save())
    except Exception as e:
        logger.error(f"[session] save_reply failed: {e}")


# ─── Logs ─────────────────────────────────────────────────────────────────────

def save_log(log_dict: dict) -> None:
    """Insert a log row into PostgreSQL logs table."""

    async def _save():
        async with get_session() as session:
            sent_at_val = None
            if log_dict.get("sent_at"):
                try:
                    sent_at_val = datetime.fromisoformat(str(log_dict["sent_at"]))
                except Exception:
                    sent_at_val = None

            record = Log(
                id=uuid.uuid4(),
                email_id=str(log_dict.get("email_id", "")),
                subject=log_dict.get("subject"),
                from_addr=log_dict.get("from_addr"),
                to_addr=log_dict.get("to_addr"),
                intent_id=log_dict.get("intent_id"),
                intent_label=log_dict.get("intent_label"),
                profile_type=log_dict.get("profile_type"),
                is_relevant=log_dict.get("is_relevant"),
                status=log_dict.get("status"),
                sent=log_dict.get("sent"),
                sent_at=sent_at_val,
                error=log_dict.get("error"),
                payload=log_dict if isinstance(log_dict, dict) else {"value": str(log_dict)},
                updated_at=datetime.now(timezone.utc),
            )
            session.add(record)
            await session.commit()

    try:
        _run(_save())
    except Exception as e:
        # Logging should never break the pipeline.
        logger.warning(f"[session] save_log skipped/failed: {e}")


# =============================================================================
# SECTION 3 — Startup test (collaborator's original)
# =============================================================================

if __name__ == "__main__":
    async def test_setup():
        try:
            await startup_database()
            print("Database setup successful!")
        except Exception as e:
            print(f"Database setup failed: {e}")
        finally:
            await shutdown_database()

    asyncio.run(test_setup())
