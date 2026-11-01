"""
scripts/email_consumer.py

Entry point for the pipeline.
Processes pending emails from the database continuously.
Runs continuously, checking every 1 minute for new emails.
"""

import sys
import os
import logging
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.batch import process_email_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # seconds


def process_emails() -> int:
    """Process all pending emails in one batch."""
    result = process_email_batch()
    return result["total"]


def run():
    """Run continuously, processing pending emails every minute."""
    logger.info("Starting continuous email consumer...")
    logger.info(f"Checking for pending emails every {CHECK_INTERVAL} seconds.")
    logger.info("Press Ctrl+C to stop.\n")

    while True:
        try:
            processed = process_emails()
            if processed == 0:
                logger.info("No pending emails. Sleeping...")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("\nShutting down gracefully...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(CHECK_INTERVAL)

    logger.info("Consumer stopped.")


if __name__ == "__main__":
    run()
