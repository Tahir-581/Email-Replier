#!/usr/bin/env python3
"""
Test script for email_sender functionality.
Sends a test email using the email_sender agent.
"""

import asyncio
import logging
from datetime import datetime, timezone

from src.agents.email_sender import email_sender
from src.pipeline.state import EmailState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def create_test_email_state() -> EmailState:
    """Create a test email state for testing email_sender."""
    return {
        "email_id": "test_email_001",
        "thread_id": "test_thread_001",
        "from_addr": "test.recipient@example.com",  # This will be the recipient
        "to_addr": "test.sender@example.com",       # This is the original sender
        "subject": "Test Email from Email Sender",
        "body": "This is a test email body to verify the email sender functionality.",
        "date": datetime.now(timezone.utc).isoformat(),
        "snippet": "Test email snippet",
        
        # Generated reply content
        "reply_subject": "Re: Test Email from Email Sender",
        "reply_body": """Hi Test User,

Thanks for your message! This is a test email sent via the email_sender agent.

We're testing the HTML email template with proper alignment and formatting. The email should include:
- Centered header with logo
- Properly aligned title section
- Left-aligned body content for readability
- Professional signature
- Centered footer with social links

Best regards,
Test Sender
Head of Operation & Talent · Test Company""",
        
        # Pipeline state
        "intent": "2",
        "intent_label": "Candidate is interested, asks for JD",
        "profile_type": "test_profile",
        "is_relevant": True,
        "processed": False,
        "sent": False,
        "status": "pending",
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_email_sender():
    """Test the email_sender function with a dummy email."""
    logger.info("🧪 Starting email_sender test")
    
    # Create test email state
    test_state = create_test_email_state()
    
    logger.info(f"📧 Test email prepared:")
    logger.info(f"   To: {test_state['from_addr']}")
    logger.info(f"   Subject: {test_state['reply_subject']}")
    logger.info(f"   Body length: {len(test_state['reply_body'])} chars")
    
    try:
        # Test email sending
        logger.info("📤 Sending test email...")
        result_state = email_sender(test_state)
        
        # Check results
        if result_state.get("sent"):
            logger.info("✅ Email sent successfully!")
            logger.info(f"   Sent at: {result_state.get('sent_at')}")
            logger.info(f"   Status: {result_state.get('status')}")
        else:
            logger.error("❌ Email sending failed!")
            logger.error(f"   Error: {result_state.get('error')}")
            
    except Exception as e:
        logger.exception("💥 Test failed with exception")
        logger.error(f"   Exception: {e}")
    
    logger.info("🏁 Email_sender test completed")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 EMAIL SENDER TEST")
    print("=" * 60)
    print("This script will send a test email using the email_sender agent.")
    print("Make sure you have configured the Gmail credentials properly.")
    print()
    
    # Confirm before sending
    response = input("Do you want to send a test email? (y/N): ").strip().lower()
    if response in ['y', 'yes']:
        test_email_sender()
    else:
        print("Test cancelled.")
    
    print()
    print("=" * 60)
