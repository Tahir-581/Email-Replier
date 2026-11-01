#!/usr/bin/env python3
"""
Interactive test script for email_sender functionality.
Allows you to specify recipient and custom email content.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (python .\scripts\...) while still importing `src.*`.
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

def _try_force_utf8_stdio() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        # Best-effort only; fall back to default console encoding.
        pass


_try_force_utf8_stdio()

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


def create_custom_email_state(recipient_email: str, subject: str, body: str) -> EmailState:
    """Create a custom email state for testing email_sender."""
    return {
        "email_id": f"test_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "thread_id": f"test_thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "from_addr": recipient_email,  # This will be the recipient
        "to_addr": "test.sender@example.com",       # This is the original sender
        "subject": subject,
        "body": "This is a test email body to verify the email sender functionality.",
        "date": datetime.now(timezone.utc).isoformat(),
        "snippet": "Test email snippet",
        
        # Generated reply content
        "reply_subject": f"Re: {subject}",
        "reply_body": body,
        
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


def test_custom_email():
    """Test email_sender with custom user input."""
    print("🧪 INTERACTIVE EMAIL SENDER TEST")
    print("=" * 50)
    
    # Get user input
    recipient = input("📧 Enter recipient email: ").strip()
    if not recipient:
        print("❌ Recipient email is required!")
        return
    
    subject = input("📝 Enter email subject: ").strip() or "Test Email from Email Sender"
    
    print("\n📄 Enter email body (press Enter twice to finish):")
    body_lines = []
    while True:
        line = input()
        if line == "" and len(body_lines) > 0 and body_lines[-1] == "":
            break
        body_lines.append(line)
    
    body = "\n".join(body_lines).strip()
    if not body:
        body = """Hi there,

This is a test email sent via the email_sender agent.

We're testing the HTML email template with proper alignment and formatting. The email should include:
- Centered header with logo
- Properly aligned title section
- Left-aligned body content for readability
- Professional signature
- Centered footer with social links

Best regards,
Test Sender
Head of Operation & Talent · Test Company"""
    
    # Create email state
    test_state = create_custom_email_state(recipient, subject, body)
    
    print(f"\n📤 Sending test email to {recipient}...")
    print(f"   Subject: {subject}")
    print(f"   Body length: {len(body)} chars")
    
    try:
        # Test email sending
        result_state = email_sender(test_state)
        
        # Check results
        if result_state.get("sent"):
            print("✅ Email sent successfully!")
            print(f"   Sent at: {result_state.get('sent_at')}")
            print(f"   Status: {result_state.get('status')}")
        else:
            print("❌ Email sending failed!")
            print(f"   Error: {result_state.get('error')}")
            
    except Exception as e:
        print(f"💥 Test failed with exception: {e}")
    
    print("\n🏁 Test completed")


def test_preset_emails():
    """Test with preset email templates."""
    print("🧪 PRESET EMAIL TEMPLATES")
    print("=" * 50)
    
    presets = {
        "1": {
            "name": "Job Application Response",
            "subject": "Re: Application for Senior AI Engineer Position",
            "body": """Dear Candidate,

Thank you for your interest in the Senior AI Engineer position at our company. We've received your application and would like to schedule an interview.

The position involves working on cutting-edge AI/ML projects with a focus on natural language processing and computer vision.

Key responsibilities:
- Design and implement ML models
- Optimize algorithms for performance
- Collaborate with cross-functional teams
- Mentor junior developers

Required qualifications:
- 3+ years of experience in ML/AI
- Strong Python programming skills
- Experience with TensorFlow/PyTorch
- PhD or Master's in Computer Science or related field

Would you be available for a technical interview next week? Please let us know your preferred time slots.

Best regards,
Hiring Team
AI/ML Department"""
        },
        "2": {
            "name": "Interview Confirmation",
            "subject": "Interview Confirmation - Senior AI Engineer",
            "body": """Hi there,

This is to confirm your interview for the Senior AI Engineer position.

Interview Details:
- Date: [Next Monday]
- Time: 2:00 PM - 3:30 PM
- Location: Video Call (Google Meet)
- Interviewers: Tech Lead + HR Representative

Interview Format:
1. Technical discussion (30 mins)
2. Coding challenge (45 mins)
3. Cultural fit discussion (15 mins)

Please ensure you have:
- Stable internet connection
- Working webcam and microphone
- Google Meet installed
- Your portfolio/projects ready to discuss

The meeting link will be sent 24 hours before the interview.

Looking forward to speaking with you!

Best regards,
Recruitment Team"""
        },
        "3": {
            "name": "Simple Test",
            "subject": "Test Email - HTML Template",
            "body": """Hello,

This is a simple test email to verify the HTML template rendering.

The email should display with:
✅ Proper alignment
✅ Centered header
✅ Left-aligned body text
✅ Professional signature
✅ Footer with social links

If you're seeing this email, the email_sender agent is working correctly!

Thanks,
Test Team"""
        }
    }
    
    print("Available presets:")
    for key, preset in presets.items():
        print(f"  {key}. {preset['name']}")
    
    choice = input("\nSelect preset (1-3): ").strip()
    
    if choice not in presets:
        print("❌ Invalid choice!")
        return
    
    recipient = input("📧 Enter recipient email: ").strip()
    if not recipient:
        print("❌ Recipient email is required!")
        return
    
    preset = presets[choice]
    test_state = create_custom_email_state(recipient, preset["subject"], preset["body"])
    
    print(f"\n📤 Sending '{preset['name']}' email to {recipient}...")
    
    try:
        result_state = email_sender(test_state)
        
        if result_state.get("sent"):
            print("✅ Email sent successfully!")
        else:
            print("❌ Email sending failed!")
            print(f"   Error: {result_state.get('error')}")
            
    except Exception as e:
        print(f"💥 Test failed: {e}")


def main():
    """Main test menu."""
    print("🧪 EMAIL SENDER TEST SUITE")
    print("=" * 50)
    print("Choose test mode:")
    print("1. Custom email (interactive)")
    print("2. Preset email templates")
    print("3. Quick simple test")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        test_custom_email()
    elif choice == "2":
        test_preset_emails()
    elif choice == "3":
        # Quick test with default values
        test_state = create_custom_email_state(
            "test.recipient@example.com",
            "Quick Test Email",
            "This is a quick test to verify email sending functionality."
        )
        try:
            result_state = email_sender(test_state)
            if result_state.get("sent"):
                print("✅ Quick test successful!")
            else:
                print("❌ Quick test failed!")
        except Exception as e:
            print(f"💥 Quick test failed: {e}")
    else:
        print("❌ Invalid choice!")


if __name__ == "__main__":
    main()
