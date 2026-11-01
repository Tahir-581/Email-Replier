"""
Email Database Writer Agent

Persists processed email data to the database.
Similar to db_writer but adapted for email processing.
"""

from __future__ import annotations

import logging
import json
from datetime import datetime
from typing import Any, Dict

import structlog
import uuid
from sqlalchemy import text
from src.db.session import get_session
from src.pipeline.state import VerificationState, VerificationUpdate
from src.utils.config import settings

logger = structlog.get_logger(__name__)


def _asyncpg_connection_kwargs() -> dict:
    """
    Build asyncpg.connect() kwargs from configured DATABASE_URL.
    Falls back to localhost defaults for local dev.
    """
    # settings.DATABASE_URL is typically SQLAlchemy async form:
    #   postgresql+asyncpg://user:pass@host:port/dbname
    dsn = (settings.DATABASE_URL or "").replace("postgresql+asyncpg://", "postgresql://", 1)
    if dsn:
        return {"dsn": dsn}

    # Local fallback (if DATABASE_URL isn't configured)
    return {
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "postgres",
        "database": settings.EMAIL_DB or "email_replier",
    }


async def create_email_record(state: VerificationState) -> str:
    """Create email record in database using direct asyncpg connection."""
    import asyncpg
    
    try:
        # Direct asyncpg connection for reliable commits (configured)
        conn = await asyncpg.connect(**_asyncpg_connection_kwargs())
        
        # Convert timezone-aware datetime to naive datetime for PostgreSQL
        import datetime
        date_value = state['date']
        if isinstance(date_value, datetime.datetime) and date_value.tzinfo is not None:
            # Remove timezone info for PostgreSQL timestamp without timezone
            date_value = date_value.replace(tzinfo=None)
        
        # Insert email record using direct connection
        result = await conn.execute("""
            INSERT INTO emails (
                id, email_id, message_id, thread_id, subject, from_addr, to_addr, 
                date, body, status, history
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
            )
            ON CONFLICT (email_id) DO UPDATE SET
                message_id = EXCLUDED.message_id,
                thread_id = EXCLUDED.thread_id,
                subject = EXCLUDED.subject,
                from_addr = EXCLUDED.from_addr,
                to_addr = EXCLUDED.to_addr,
                date = EXCLUDED.date,
                body = EXCLUDED.body,
                status = CASE
                    WHEN emails.status IN ('processed', 'irrelevant') THEN emails.status
                    ELSE EXCLUDED.status
                END
            RETURNING id
        """, 
            uuid.uuid4(),
            state['email_id'],
            state['message_id'],
            state['thread_id'],
            state['subject'],
            state['from_addr'],
            state['to_addr'],
            date_value,
            state['body'],
            state.get('status', 'pending'),
            json.dumps(state.get("history") or []),
        )
        
        # Get the returned ID
        email_db_id = result.split(' ')[-1] if result else None
        
        await conn.close()
        
        logger.info(f"Created email record: {state['email_id']} -> DB ID: {email_db_id}")
        return email_db_id
        
    except Exception as e:
        logger.error(f"Failed to create email record: {e}")
        raise


async def update_email_record(email_id: str, updates: VerificationUpdate) -> bool:
    """Update email record in database with all fields support."""
    async with get_session() as session:
        async with session.begin():
            # Build update query dynamically
            set_clauses = []
            params = {'email_id': email_id}
            
            for key, value in updates.items():
                # Support essential fields only (no history temporarily)
                if key in ['status', 'message_id', 'thread_id', 'subject', 'from_addr', 
                          'to_addr', 'date', 'body']:
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value
            
            if not set_clauses:
                return False
            
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            
            query = text(f"""
                UPDATE emails 
                SET {', '.join(set_clauses)}
                WHERE email_id = :email_id
            """)
            
            result = await session.execute(query, params)
            
            if result.rowcount > 0:
                logger.info(f"Updated email record: {email_id}")
                return True
            else:
                logger.warning(f"No email record found to update: {email_id}")
                return False




async def email_db_writer(state: VerificationState) -> VerificationState:
    """
    Main email database writer agent.
    Persists email data to database with thread history support.
    """
    email_id = state['email_id']
    
    try:
        logger.info(f"Writing email {email_id} to database with thread history")
        
        # Log thread history info
        if state.get('history'):
            logger.info(f"   📜 Thread history: {len(state['history'])} messages")
        
        # Create or update email record
        email_db_id = await create_email_record(state)
        
        # Update state with database ID
        updated_state = state.copy()
        if email_db_id:
            updated_state['email_db_id'] = email_db_id
        
        logger.info(f"Successfully wrote email {email_id} to database")
        return updated_state
        
    except Exception as e:
        logger.error(f"Error writing email {email_id} to database: {e}")
        
        # Add error to state
        updated_state = state.copy()
        updated_state['errors'] = state.get('errors', []) + [f"db_writer_error: {str(e)}"]
        updated_state['failed_node'] = 'email_db_writer'
        
        return updated_state


async def get_email_by_id(email_id: str) -> Dict[str, Any]:
    """Get email record from database with thread history."""
    async with get_session() as session:
        query = text("""
            SELECT * FROM emails 
            WHERE email_id = :email_id
        """)
        
        result = await session.execute(query, {'email_id': email_id})
        
        row = result.fetchone()
        
        if row:
            return {
                'id': str(row[0]),
                'email_id': row[1],
                'message_id': row[2],
                'thread_id': row[3],
                'subject': row[4],
                'from_addr': row[5],
                'to_addr': row[6],
                'date': row[7],
                'body': row[8],
                'status': row[9],
                'created_at': row[10],
                'updated_at': row[11]
            }
        
        return None


