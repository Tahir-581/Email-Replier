"""
Database setup script for email replier.

Initializes PostgreSQL database and creates initial migration.
"""

import os
import subprocess
import sys
from pathlib import Path

import structlog

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.utils.config import settings

logger = structlog.get_logger(__name__)


def setup_database():
    """Set up the database with initial migration."""
    try:
        # Change to the src/db directory for alembic
        db_dir = project_root / "src" / "db"
        os.chdir(db_dir)
        
        # Create initial migration
        logger.info("Creating initial database migration...")
        result = subprocess.run([
            sys.executable, "-m", "alembic", 
            "revision", "--autogenerate", "-m", "Initial email table"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Failed to create migration: {result.stderr}")
            return False
        
        logger.info("Initial migration created successfully")
        
        # Run the migration
        logger.info("Running database migration...")
        result = subprocess.run([
            sys.executable, "-m", "alembic", "upgrade", "head"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Failed to run migration: {result.stderr}")
            return False
        
        logger.info("Database migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        return False


def check_environment():
    """Check if required environment variables are set."""
    required_vars = [
        "DATABASE_URL",
        "DATABASE_BASE_URL",
        "EMAIL_DB"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not getattr(settings, var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        logger.info("Please set these in your .env file:")
        logger.info("DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/email_replier")
        logger.info("DATABASE_BASE_URL=postgresql+asyncpg://username:password@localhost:5432/")
        logger.info("TWITTER_DB=email_replier")
        return False
    
    return True


if __name__ == "__main__":
    logger.info("Starting database setup...")
    
    # Check environment
    if not check_environment():
        sys.exit(1)
    
    # Setup database
    if setup_database():
        logger.info("Database setup completed successfully!")
    else:
        logger.error("Database setup failed!")
        sys.exit(1)
