"""
Email pipeline state management.

Defines state structures and utility functions for the email processing pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict, Union


class EmailState(TypedDict, total=False):
    """Core email state structure."""
    email_id: str
    message_id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    date: datetime
    body: str
    status: str
    errors: List[str]
    created_at: datetime
    updated_at: datetime


class VerificationState(TypedDict, total=False):
    """Complete unified state for the full email processing pipeline.
    Contains all fields from both collaborator's and our pipeline.
    """

    # ── Raw email attributes (shared) ────────────────────────────
    id: str
    email_id: str
    message_id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    body: str
    date: datetime
    received_at: str
    status: str

    # ── Collaborator: Layer 1+2 fields ────────────────────────────
    history: List[Dict[str, Any]]
    email_db_id: str
    errors: List[str]
    retry_count: int
    failed_node: Optional[str]
    thread_participants: Optional[List[str]]

    # ── Node 1: is_related output ────────────────────────────────────
    is_related: Optional[bool]
    related_reason: Optional[str]

    # ── Node 2: check_history output ────────────────────────────────────
    history_analysis: Optional[str]

    # ── Additional unified fields (GraphState parity) ────────────────────
    candidate_name: str
    email_summary: str
    detected_concerns: List[str]
    detected_intents: List[Dict[str, Any]]
    detected_intents_json: str
    primary_intent_id: int
    primary_intent_label: str
    forms_already_shared: bool
    concern_count: int
    intent_id: int
    intent_label: str

    # ── Node 3: intent classifier output ────────────────────────────────────
    intent_type: str
    profile_type: str

    # ── Node 4: policy agent output ────────────────────────────────────
    policy: Optional[str]
    reply_constraints: Dict[str, Any]
    is_linkedin: bool
    form_type: Optional[str]

    # ── Node 5: email writer agent output ────────────────────────────────────
    reply_content: Optional[str]
    reply_tone: Optional[str]
    reply_length: Optional[str]
    reply_generated: bool

    # ── Node 6: email sender agent output ────────────────────────────────────
    email_sent: bool
    sent_at: Optional[datetime]

    # ── Node 7: logs writer agent output ────────────────────────────────────
    processing_summary: Optional[Dict[str, Any]]

    # ── Timestamps ────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime


class VerificationUpdate(TypedDict, total=False):
    """Email verification update structure."""
    status: str
    errors: List[str]
    updated_at: datetime


# Type aliases for compatibility
EmailState = VerificationState


def create_verification_state(
    email_id: str,
    message_id: str,
    thread_id: str,
    subject: str,
    from_addr: str,
    to_addr: str,
    date: datetime,
    body: str,
    history: List[Dict[str, Any]] = None
) -> VerificationState:
    """Create initial verification state."""
    return {
        "id": email_id,
        "email_id": email_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "subject": subject,
        "from_addr": from_addr,
        "to_addr": to_addr,
        "date": date,
        "received_at": date.isoformat() if isinstance(date, datetime) else str(date),
        "body": body,
        "status": "pending",
        "history": history or [],
        "email_db_id": "",
        "errors": [],
        "retry_count": 0,
        "failed_node": None,
        "thread_participants": None,
        "is_related": None,
        "related_reason": None,
        "history_analysis": None,
        "candidate_name": "",
        "email_summary": "",
        "detected_concerns": [],
        "detected_intents": [],
        "detected_intents_json": "",
        "primary_intent_id": 0,
        "primary_intent_label": "",
        "forms_already_shared": False,
        "concern_count": 0,
        "intent_id": 0,
        "intent_label": "",
        "intent_type": "",
        "profile_type": "",
        "policy": None,
        "reply_constraints": {},
        "is_linkedin": False,
        "form_type": None,
        "reply_content": None,
        "reply_tone": None,
        "reply_length": None,
        "reply_generated": False,
        "email_sent": False,
        "sent_at": None,
        "processing_summary": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


def create_email_state(
    email_id: str,
    message_id: str,
    thread_id: str,
    subject: str,
    from_addr: str,
    to_addr: str,
    date: datetime,
    body: str,
    history: List[Dict[str, Any]] = None
) -> EmailState:
    """Create initial email state (alias for verification state)."""
    return create_verification_state(
        email_id, message_id, thread_id, subject, 
        from_addr, to_addr, date, body, history
    )


def update_verification_state(
    state: VerificationState,
    updates: VerificationUpdate
) -> VerificationState:
    """Update verification state with new values."""
    updated_state = state.copy()
    updated_state.update(updates)
    updated_state["updated_at"] = datetime.now()
    return updated_state


def is_email_processed(state: VerificationState) -> bool:
    """Check if email has been processed."""
    return state.get("status") == "completed"


def has_errors(state: VerificationState) -> bool:
    """Check if email has processing errors."""
    return len(state.get("errors", [])) > 0


def get_error_summary(state: VerificationState) -> str:
    """Get error summary from state."""
    errors = state.get("errors", [])
    return "; ".join(str(error) for error in errors)


def get_processing_summary(state: VerificationState) -> Dict[str, Any]:
    """Get processing summary from state."""
    return {
        "email_id": state.get("email_id"),
        "status": state.get("status"),
        "errors": state.get("errors", []),
        "has_errors": has_errors(state),
        "is_processed": is_email_processed(state),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
    }


def clean_email_addr(email_str: str) -> str:
    """Clean email address - remove names, keep only email."""
    if '<' in email_str and '>' in email_str:
        return email_str.split('<')[1].split('>')[0].strip()
    return email_str.strip()


def create_state_from_gmail_email(gmail_email: Dict[str, Any]) -> EmailState:
    """Create email state from Gmail email data."""
    from email.utils import parsedate_to_datetime
    import datetime
    
    # Parse date string to datetime
    date_str = gmail_email.get('date', '')
    try:
        email_date = parsedate_to_datetime(date_str)
        if email_date.tzinfo is None:
            email_date = email_date.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        email_date = datetime.now(datetime.timezone.utc)
    
    return create_email_state(
        email_id=gmail_email.get("id", gmail_email.get("email_id", "")),
        message_id=gmail_email.get("message_id", gmail_email.get("id", "")),
        thread_id=gmail_email.get("thread_id", gmail_email.get("id", "")),
        subject=gmail_email.get("subject", ""),
        from_addr=clean_email_addr(gmail_email.get("from", gmail_email.get("from_addr", ""))),
        to_addr=clean_email_addr(gmail_email.get("to", gmail_email.get("to_addr", ""))),
        date=email_date,
        body=gmail_email.get("body", ""),
        history=gmail_email.get("history", [])
    )


def update_status(state: VerificationState, status: str) -> VerificationState:
    """Update verification state status."""
    return update_verification_state(state, {'status': status})


# Type alias for better readability
EmailUpdate = VerificationUpdate  # For backward compatibility
