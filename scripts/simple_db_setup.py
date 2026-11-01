"""
Simple Database Setup

Creates the email_replier database and emails table without Alembic.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import asyncpg
import structlog
from src.utils.config import settings

logger = structlog.get_logger(__name__)


async def create_database():
    """Create the email_replier database."""
    try:
        # Parse database URL from settings
        from urllib.parse import urlparse
        
        database_url = settings.DATABASE_URL
        if not database_url:
            raise ValueError("DATABASE_URL not configured in settings")
        
        parsed = urlparse(database_url)
        conn_params = {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "user": parsed.username,
            "password": parsed.password,
            "database": "postgres"  # Connect to default postgres database
        }
        
        db_name = parsed.path.lstrip("/") or "email_replier"
        
        conn = await asyncpg.connect(**conn_params)
        result = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        
        if not result:
            # Create database
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info(f"Database '{db_name}' created successfully")
        else:
            logger.info(f"Database '{db_name}' already exists")
        
        await conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        return False


async def create_emails_table():
    """Create the emails table."""
    try:
        # Parse database URL from settings
        from urllib.parse import urlparse
        
        database_url = settings.DATABASE_URL
        if not database_url:
            raise ValueError("DATABASE_URL not configured in settings")
        
        parsed = urlparse(database_url)
        conn_params = {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "user": parsed.username,
            "password": parsed.password,
            "database": parsed.path.lstrip("/") or "email_replier"
        }
        
        conn = await asyncpg.connect(**conn_params)
        
        # Create emails table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email_id VARCHAR UNIQUE NOT NULL,
                message_id VARCHAR,
                thread_id VARCHAR,
                subject TEXT,
                from_addr VARCHAR,
                to_addr VARCHAR,
                date TIMESTAMP,
                body TEXT,
                status VARCHAR DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create replies table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email_id VARCHAR NOT NULL,
                thread_id VARCHAR,
                from_addr VARCHAR,
                to_addr VARCHAR,
                subject TEXT,
                body TEXT,
                intent_id INTEGER,
                intent_label VARCHAR,
                profile_type VARCHAR,
                sender_name VARCHAR,
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        logger.info("Database tables created successfully")
        await conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        return False


async def main():
    """Main setup function."""
    logger.info("Starting simple database setup...")
    
    # Create database
    if not await create_database():
        logger.error("Database creation failed!")
        sys.exit(1)
    
    # Create table
    if not await create_emails_table():
        logger.error("Table creation failed!")
        sys.exit(1)
    
    logger.info("✅ Database setup completed successfully!")
    print("Database setup completed successfully!")
    print("You can now run: python scripts/run_pipeline.py --limit 5")


if __name__ == "__main__":
    asyncio.run(main())
