"""
Gmail Email Fetcher - OAuth2 Production Version
==============================================

✔ Works with google-auth-oauthlib token
✔ Safe token loading (no manual parsing)
✔ Auto refresh support
✔ Clean Gmail API integration
"""

import json
import time
import asyncio
import random
import socket
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import structlog
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.utils.config import PROJECT_ROOT as _CONFIG_ROOT
from src.utils.config import settings

logger = structlog.get_logger(__name__)

# =========================
# CONFIG
# =========================
SCOPES = ["https://mail.google.com/"]


def _token_path() -> Path:
    p = Path(settings.GMAIL_TOKEN_FILE)
    return p if p.is_absolute() else _CONFIG_ROOT / p


class GmailPullerOAuth2:
    """Gmail fetcher using proper OAuth2 token flow."""

    def __init__(self):
        self.token_file = _token_path()
        self.service = None
        self.creds = None
        self.user_email = ''  # Will be set after authentication
        self.processed_emails: Set[str] = set()  # Track processed email IDs
        self.last_check_time = time.time() - 30  # Initialize to trigger immediate check

        logger.info("Gmail Puller initialized", token_file=str(self.token_file))

    def get_user_email(self) -> str:
        """Get the authenticated Gmail user's email address."""
        return self.user_email

    # =========================
    # AUTH
    # =========================
    def _load_token(self) -> Optional[Credentials]:
        """Load OAuth2 credentials safely."""

        try:
            if not self.token_file.exists():
                logger.error("Token file not found. Run setup script first.")
                return None

            creds = Credentials.from_authorized_user_file(
                str(self.token_file),
                SCOPES
            )

            return creds

        except Exception as e:
            logger.error("Failed to load token", error=str(e))
            return None

    def _refresh_token(self, creds: Credentials) -> Optional[Credentials]:
        """Refresh token if expired."""

        try:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing token...")
                creds.refresh(Request())

                # Save updated token
                with open(self.token_file, "w") as f:
                    f.write(creds.to_json())

                logger.info("Token refreshed successfully")
                return creds

            if not creds.valid:
                logger.error("Token invalid. Re-run OAuth setup.")
                return None

            return creds

        except Exception as e:
            logger.error("Token refresh failed", error=str(e))
            return None

    # =========================
    # SERVICE
    # =========================
    def _get_service(self):
        if self.service:
            return self.service

        creds = self._load_token()
        if not creds:
            return None

        creds = self._refresh_token(creds)
        if not creds:
            return None

        try:
            self.service = build("gmail", "v1", credentials=creds)
            self.creds = creds

            # Get user email from profile
            try:
                profile = self.service.users().getProfile(userId='me').execute()
                self.user_email = profile.get('emailAddress', '')
                logger.info("Gmail service ready", user_email=self.user_email)
            except Exception:
                self.user_email = ''
                logger.info("Gmail service ready (email unknown)")

            return self.service

        except Exception as e:
            logger.error("Failed to build Gmail service", error=str(e))
            return None

    # =========================
    # FETCH EMAILS
    # =========================
    async def fetch_emails(
        self,
        limit: int = 50,
        query: str = ""
    ) -> List[Dict[str, Any]]:

        service = self._get_service()
        if not service:
            return []

        # Add retry logic for Gmail API calls
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                results = service.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=limit
                ).execute()
                break  # Success, exit retry loop
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    raise e
                logger.warning(f"Gmail API attempt {attempt + 1} failed, retrying in {retry_delay}s: {e}")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff

        messages = results.get("messages", [])

        if not messages:
            logger.info("No emails found")
            return []

        emails = []

        for msg_meta in messages:
            try:
                # Skip if already processed
                if msg_meta["id"] in self.processed_emails:
                    continue

                msg = service.users().messages().get(
                    userId="me",
                    id=msg_meta["id"],
                    format="full"
                ).execute()

                headers = {
                    h["name"]: h["value"]
                    for h in msg["payload"].get("headers", [])
                }

                subject = headers.get("Subject", "").strip()
                from_addr = headers.get("From", "").strip()
                
                # Skip emails with empty subject (system/internal emails)
                if not subject:
                    logger.debug(f"Skipping email {msg['id']}: Empty subject - likely system email")
                    continue
                
                email_data = {
                    "id": msg["id"],
                    "thread_id": msg.get("threadId"),
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "body": self._extract_body(msg["payload"]),
                    "snippet": msg.get("snippet", "")
                }

                emails.append(email_data)
                self.processed_emails.add(msg["id"])  # Mark as processed

            except Exception as e:
                logger.warning("Email processing failed", error=str(e))
                continue

        logger.info("Emails fetched", count=len(emails))
        return emails

    # =========================
    # THREAD HISTORY FETCHER
    # =========================
    async def _fetch_thread_history(self, service, thread_id: str) -> List[Dict[str, Any]]:
        """Fetch complete thread history using thread_id."""
        if not thread_id:
            return []

        try:
            # Get thread details
            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="metadata"
            ).execute()

            history = []
            messages = thread.get("messages", [])

            for msg in messages:
                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }

                msg_data = {
                    "id": msg["id"],
                    "thread_id": msg.get("threadId"),
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", "")
                }
                history.append(msg_data)

            return history

        except Exception as e:
            logger.warning("Thread history fetch failed", thread_id=thread_id, error=str(e))
            return []

    # =========================
    # POLLING EMAIL FETCHER
    # =========================
    async def fetch_new_emails(
        self,
        limit: int = 50,
        query: str = "",
        polling_interval: int = 30,
        last_hours: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Fetch new emails from last N hours with polling and duplicate prevention."""

        current_time = time.time()

        # Check if enough time has passed since last check
        if current_time - self.last_check_time < polling_interval:
            logger.info("Skipping email fetch - too soon since last check")
            return []

        self.last_check_time = current_time

        # Fetch emails from last N hours - filter in Python for reliability
        from datetime import datetime, timedelta
        try:
            last_hours_value = float(last_hours)
        except Exception:
            last_hours_value = 1.0
        if last_hours_value <= 0:
            last_hours_value = 1.0

        cutoff_time = datetime.now() - timedelta(hours=last_hours_value)
        
        # Don't use time filter in Gmail query - get recent emails and filter in Python
        # This avoids Gmail API time filter inconsistencies
        if query:
            # Keep existing query but don't add time filter
            pass  # Use query as-is
        else:
            # No query - get recent emails without time filter
            query = ""

        logger.info(f"Checking for new emails from last {last_hours_value:g} hour(s)", query=query)

        # Fetch today's emails and filter by actual time in Python
        all_emails = await self.fetch_emails(limit, query)
        
        # Filter emails by actual timestamp (last N hours only)
        recent_emails = []
        
        for email in all_emails:
            try:
                from email.utils import parsedate_to_datetime
                if email.get('date'):
                    email_date = parsedate_to_datetime(email['date'])
                    if email_date:
                        # Convert both to naive datetime for proper comparison
                        current_time = datetime.now()
                        
                        # Convert email_date to naive datetime (remove timezone)
                        if email_date.tzinfo is not None:
                            email_date_naive = email_date.replace(tzinfo=None)
                        else:
                            email_date_naive = email_date
                        
                        # cutoff_time is already naive datetime
                        cutoff_time_naive = cutoff_time
                        
                        if email_date_naive >= cutoff_time_naive:
                            recent_emails.append(email)
                            age_minutes = (current_time - email_date_naive).total_seconds() / 60
                            logger.info(f"✅ Recent email found: {email['subject'][:30]}... ({age_minutes:.1f} min old)")
                        else:
                            age_minutes = (current_time - email_date_naive).total_seconds() / 60
                            logger.debug(f"⏰ Skipping old email: {email['subject'][:30]}... ({age_minutes:.1f} min old)")
                    else:
                        logger.warning(f"Could not parse date for email {email['id']}: no date parsed")
                else:
                    logger.warning(f"Email {email['id']} has no date header")
            except Exception as e:
                logger.warning(f"Could not parse date for email {email['id']}: {e}")
                # Skip emails with unparseable dates (better than including wrong ones)
                continue
        
        logger.info(f"Filtered to {len(recent_emails)} truly recent emails from last {last_hours_value:g} hour(s)")
        return recent_emails

    # =========================
    async def start_continuous_polling(
        self,
        callback=None,
        limit: int = 50,
        polling_interval: int = 30
    ):
        """Start continuous email polling."""
        logger.info(f"Starting continuous polling every {polling_interval} seconds")

        while True:
            try:
                new_emails = await self.fetch_new_emails(limit, polling_interval=polling_interval)

                if new_emails and callback:
                    await callback(new_emails)

                await asyncio.sleep(polling_interval)

            except Exception as e:
                logger.error("Polling error", error=str(e))
                await asyncio.sleep(polling_interval)

    # =========================
    # BODY PARSER
    # =========================
    def _decode(self, data: str) -> str:
        try:
            data = data.replace("-", "+").replace("_", "/")
            padding = "=" * (-len(data) % 4)
            return base64.b64decode(data + padding).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _extract_body(self, payload) -> str:
        try:
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        return self._decode(part["body"].get("data", ""))

            return self._decode(payload.get("body", {}).get("data", ""))

        except Exception as e:
            logger.warning("Body extraction failed", error=str(e))
            return ""

    # =========================
    # SEND EMAIL
    # =========================
    async def send_email(self, to: str, subject: str, body: str, html: str = None) -> bool:
        service = self._get_service()
        if not service:
            return False

        def _is_transient_send_error(exc: Exception) -> bool:
            # Windows "connection aborted by software in your host machine"
            if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10053:
                return True

            if isinstance(exc, (TimeoutError, ConnectionError, ConnectionResetError, socket.timeout)):
                return True

            # HttpError (e.g. quota / backend flake)
            if isinstance(exc, HttpError):
                try:
                    status = int(getattr(exc.resp, "status", 0) or 0)
                except Exception:
                    status = 0
                if status in (408, 429) or 500 <= status <= 599:
                    return True

            msg = str(exc).lower()
            if any(
                token in msg
                for token in (
                    "timed out",
                    "timeout",
                    "connection aborted",
                    "connection reset",
                    "connection closed",
                    "remote end closed connection",
                    "tlsv",
                    "ssl",
                    "temporarily unavailable",
                )
            ):
                return True

            return False

        max_attempts = 5
        base_delay_s = 1.0

        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            if html:
                # Create multipart message with both plain text and HTML
                message = MIMEMultipart("alternative")
                message["to"] = to
                message["subject"] = subject

                # Attach plain text part
                text_part = MIMEText(body, "plain")
                message.attach(text_part)

                # Attach HTML part
                html_part = MIMEText(html, "html")
                message.attach(html_part)
            else:
                # Plain text only
                message = MIMEText(body)
                message["to"] = to
                message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    # googleapiclient has built-in retries, but we wrap it to
                    # handle OS/network resets consistently (e.g. WinError 10053).
                    service.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=3)
                    logger.info("Email sent", to=to, has_html=bool(html))
                    return True
                except Exception as e:
                    last_exc = e
                    if attempt >= max_attempts or not _is_transient_send_error(e):
                        raise

                    # Exponential backoff with jitter
                    delay = base_delay_s * (2 ** (attempt - 1))
                    delay = min(delay, 20.0)
                    delay = delay + random.random() * 0.25 * delay
                    logger.warning(
                        "Send email transient failure; retrying",
                        to=to,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_s=round(delay, 2),
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

            # Should be unreachable, but keep a safe fallback
            if last_exc is not None:
                raise last_exc
            return False

        except Exception as e:
            logger.error("Send email failed", error=str(e))
            return False

    # =========================
    # CREATE DRAFT
    # =========================
    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        html: str = None,
        thread_id: str | None = None,
    ) -> str | None:
        """
        Create a Gmail draft with the provided content (does NOT send).

        Returns:
            draft_id (str) on success, None on failure.
        """
        service = self._get_service()
        if not service:
            return None

        try:
            from email.mime.text import MIMEText

            # For drafts, prefer a single text/html body when available so the
            # Gmail UI opens the draft in rich-text mode (clickable links,
            # paragraph spacing, signature formatting).
            if html:
                message = MIMEText(html, "html", "utf-8")
            else:
                message = MIMEText(body, "plain", "utf-8")

            message["to"] = to
            message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            msg_body: dict[str, Any] = {"raw": raw}
            if thread_id:
                msg_body["threadId"] = thread_id

            draft = (
                service.users()
                .drafts()
                .create(userId="me", body={"message": msg_body})
                .execute(num_retries=3)
            )
            draft_id = draft.get("id")
            logger.info("Draft created", to=to, has_html=bool(html), draft_id=draft_id)
            return draft_id
        except Exception as e:
            logger.error("Create draft failed", error=str(e))
            return None


# =========================
# SINGLETON
# =========================
_puller = None


def get_gmail_puller():
    global _puller
    if _puller is None:
        _puller = GmailPullerOAuth2()
    return _puller


# =========================
# TEST
# =========================
async def test():
    print("Testing Gmail Puller with new features...\n")

    puller = get_gmail_puller()
    
    # Test regular fetch
    print("📧 Testing regular email fetch...")
    emails = await puller.fetch_emails(limit=3)

    if not emails:
        print("❌ No emails found. Run OAuth setup first.")
        return

    for i, e in enumerate(emails, 1):
        print(f"{i}. {e['subject']} ({e['from']})")
        if e.get('history'):
            print(f"   📜 Thread history: {len(e['history'])} messages")
        print()

    # Test new emails fetch
    print("🔍 Testing new emails fetch...")
    new_emails = await puller.fetch_new_emails(limit=5)
    print(f"Found {len(new_emails)} new emails")

    # Test duplicate prevention
    print("🔄 Testing duplicate prevention...")
    duplicate_emails = await puller.fetch_emails(limit=3)
    print(f"Duplicate check: {len(duplicate_emails)} emails (should be 0)")


async def test_continuous_polling():
    """Test continuous polling for 2 minutes."""
    print("🔄 Testing continuous polling (2 minutes)...")
    
    async def email_callback(new_emails):
        print(f"📧 Found {len(new_emails)} new emails:")
        for email in new_emails:
            print(f"   - {email['subject'][:50]}... from {email['from']}")
    
    puller = get_gmail_puller()
    
    try:
        await puller.start_continuous_polling(
            callback=email_callback,
            limit=5,
            polling_interval=30
        )
    except KeyboardInterrupt:
        print("\n⏹️ Polling stopped by user")


if __name__ == "__main__":
    import asyncio
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--poll":
        asyncio.run(test_continuous_polling())
    else:
        asyncio.run(test())