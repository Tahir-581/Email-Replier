import asyncio
import html
import logging
import re
import threading
import time
from datetime import datetime, timezone, timedelta

from src.gmail_puller import get_gmail_puller
from src.db.session import save_reply, update_email_status
from src.pipeline.state import EmailState
from src.utils.config import (
    COMPANY_NAME,
    COMPANY_WEBSITE,
    LINKEDIN_URL,
    RECRUITER_EMAIL,
    RECRUITER_NAME,
    RECRUITER_TITLE,
    SALARY_SENIOR,
    WORK_LOCATION,
    SEND_EMAILS_DIRECTLY,
)

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"(https?://[^\s<>()]+)", re.IGNORECASE)
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\u2022)\s+")


def _linkify_html_escaped_text(escaped_text: str) -> str:
    if not escaped_text:
        return ""

    def _repl(match: re.Match) -> str:
        url = match.group(1)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'

    return _URL_RE.sub(_repl, escaped_text)


def _is_bullet_line(stripped: str) -> bool:
    return bool(stripped) and bool(_BULLET_PREFIX_RE.match(stripped))


def _strip_bullet_prefix(stripped: str) -> str:
    return _BULLET_PREFIX_RE.sub("", stripped, count=1).strip()


def _render_paragraph_html(stripped_line: str) -> str:
    escaped = html.escape(stripped_line)
    escaped = _linkify_html_escaped_text(escaped)
    return f'<p style="margin:0 0 10px;line-height:1.5;">{escaped}</p>'


def _render_bullet_list_html(items: list[str]) -> str:
    li_html: list[str] = []
    for raw in items:
        escaped = html.escape(raw)
        escaped = _linkify_html_escaped_text(escaped)
        li_html.append(f'<li style="margin:0 0 4px;line-height:1.5;">{escaped}</li>')
    return (
        '<ul style="margin:0 0 10px;padding-left:22px;">'
        + "".join(li_html)
        + "</ul>"
    )


def _text_to_simple_html(text: str) -> str:
    """
    Convert plain text reply into lightweight HTML for Gmail drafts.

    Rendering rules (designed to feel hand-written, not bot-spaced):
      - Each non-empty line becomes a <p> with a tight bottom margin.
      - Blank / whitespace-only lines are SKIPPED (paragraph margins do the
        spacing work). This avoids the "double-spaced" look caused when the
        LLM emits `\\n\\n` or `\\n \\n` between every paragraph.
      - Consecutive lines starting with `- `, `* `, or `•` are collapsed into
        a single <ul><li>...</li></ul> bullet list. Stray blank lines between
        bullet lines are tolerated so a mid-list newline does not break the
        list into three separate "paragraphs" in Gmail.
      - URLs are converted into clickable <a> links.
    """
    lines = (text or "").splitlines()
    chunks: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        if _is_bullet_line(stripped):
            items: list[str] = [_strip_bullet_prefix(stripped)]
            j = i + 1
            while j < n:
                next_stripped = lines[j].strip()
                if not next_stripped:
                    k = j + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and _is_bullet_line(lines[k].strip()):
                        j = k
                        continue
                    break
                if _is_bullet_line(next_stripped):
                    items.append(_strip_bullet_prefix(next_stripped))
                    j += 1
                    continue
                break
            chunks.append(_render_bullet_list_html(items))
            i = j
            continue

        chunks.append(_render_paragraph_html(stripped))
        i += 1

    return "".join(chunks) or "<p></p>"


def _display_name_from_email(address: str) -> str:
    local = (address or "").split("@", 1)[0].strip()
    if not local:
        return "there"
    parts = [part for part in re.split(r"[._+-]+", local) if part]
    if not parts:
        return "there"
    return " ".join(part.capitalize() for part in parts)


def _initials_from_name(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "LX"
    return "".join(part[0] for part in parts[:2]).upper()


def _get_gmail_user_email() -> str:
    """Get the authenticated Gmail user's email address."""
    puller = get_gmail_puller()
    # Ensure service is initialized to get user email
    service = puller._get_service()
    if service:
        return puller.get_user_email()
    return ""


def _get_initials(name: str) -> str:
    """Get initials from a name (e.g., 'Alex Recruiter' -> 'AR')."""
    # Temporary fix: Use hardcoded name if config is empty
    if not name:
        name = "Alex Recruiter"
    parts = name.strip().split()
    initials = "".join([part[0].upper() for part in parts if part])
    return initials[:2]  # Max 2 initials


def _run_async(coro):
    try:
      asyncio.get_running_loop()
    except RuntimeError:
      return asyncio.run(coro)

    result = {}
    error = {}

    def runner() -> None:
        try:

          result["value"] = asyncio.run(coro)
        except BaseException as exc:
            # pragma: no cover - sync bridge safety
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


def _create_draft_via_gmail_oauth(
    to_addr: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    thread_id: str | None = None,
) -> str:
    """Create a Gmail draft via OAuth (does NOT send). Returns draft id."""
    puller = get_gmail_puller()
    draft_id = _run_async(
        puller.create_draft(
            to=to_addr,
            subject=subject,
            body=body,
            html=html_body,
            thread_id=thread_id,
        )
    )
    if not draft_id:
        raise RuntimeError("Gmail OAuth draft creation failed")
    return str(draft_id)


def _send_email_via_gmail_oauth(
    to_addr: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> bool:
    """Send an email via Gmail OAuth. Returns True if successful."""
    puller = get_gmail_puller()
    success = _run_async(
        puller.send_email(
            to=to_addr,
            subject=subject,
            body=body,
            html=html_body,
        )
    )
    if not success:
        raise RuntimeError("Gmail OAuth email send failed")
    return success


def email_sender(state: EmailState) -> EmailState:
    """
    Agent 6 - Email Sender.
    Sends email directly via Gmail OAuth or creates a draft, based on SEND_EMAILS_DIRECTLY setting.
    """
    logger.info(f"[EmailSender] email_id={state['email_id']}")
    logger.info(f"[EmailSender] SEND_EMAILS_DIRECTLY={SEND_EMAILS_DIRECTLY}")

    # Idempotency within a single pipeline run: if we already sent/drafted, never re-send.
    if state.get("sent") is True and state.get("sent_at"):
        logger.info("[EmailSender] Skipping send (already processed in this run)")
        return state

    to_addr = state.get("from_addr", "")
    subject = state.get("reply_subject", f"Re: {state.get('subject', '')}")
    body = state.get("reply_body", "").strip()
    draft_html_body = _text_to_simple_html(body)

    # Get Gmail user email BEFORE building HTML so footer shows correct sender
    gmail_sender_email = _get_gmail_user_email()
    logger.info(f"[EmailSender] DEBUG - Gmail sender email='{gmail_sender_email}'")

    # DEBUG: Log config values to diagnose issues
    logger.info(f"[EmailSender] DEBUG - RECRUITER_NAME='{RECRUITER_NAME}'")
    logger.info(f"[EmailSender] DEBUG - RECRUITER_TITLE='{RECRUITER_TITLE}'")
    logger.info(f"[EmailSender] DEBUG - RECRUITER_EMAIL='{RECRUITER_EMAIL}'")
    logger.info(f"[EmailSender] DEBUG - body length={len(body)}")
    logger.info(f"[EmailSender] DEBUG - body preview={body[:100] if body else 'EMPTY'}")

    if not to_addr:
        state["sent"] = False
        state["error"] = "Missing recipient email address"
        logger.error("[EmailSender] Missing recipient email address")
        return state

    if not body:
        state["sent"] = False
        state["error"] = "Reply body is empty"
        logger.error("[EmailSender] Reply body is empty")
        return state

    # Guard against repeated attempts inside the same run.
    # (The pipeline graph may revisit nodes on error; also protects against
    # accidental double-invocation.)
    max_attempts = 3
    attempts = int(state.get("_send_attempts", 0) or 0)
    if attempts >= max_attempts:
        state["sent"] = False
        state["error"] = f"Email send failed: exceeded max attempts ({max_attempts})"
        logger.error("[EmailSender] Send skipped: max attempts exceeded")
        return state

    state["_send_attempts"] = attempts + 1

    # Choose send method based on configuration
    send_method = "Gmail OAuth (send)" if SEND_EMAILS_DIRECTLY else "Gmail OAuth (draft)"
    last_exc: Exception | None = None
    draft_id: str | None = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            if SEND_EMAILS_DIRECTLY:
                # Send email directly
                success = _send_email_via_gmail_oauth(
                    to_addr=to_addr,
                    subject=subject,
                    body=body,
                    html_body=draft_html_body,
                )
                if success:
                    last_exc = None
                    break
            else:
                # Create draft
                draft_id = _create_draft_via_gmail_oauth(
                    to_addr=to_addr,
                    subject=subject,
                    body=body,
                    html_body=draft_html_body,
                    thread_id=state.get("thread_id") or None,
                )
                last_exc = None
                break
        except Exception as exc:
            last_exc = exc
            # If this looks like WinError 10053 or similar transient network reset,
            # back off a bit and retry.
            msg = str(exc).lower()
            is_transient = "10053" in msg or "connection aborted" in msg or "timed out" in msg or "timeout" in msg
            if attempt >= max_attempts or not is_transient:
                break
            delay_s = min(2 ** (attempt - 1), 5)
            logger.warning("[EmailSender] Transient send failure; retrying in %ss: %s", delay_s, exc)
            time.sleep(delay_s)

    if last_exc is not None:
        state["sent"] = False
        state["error"] = f"Email send failed: {last_exc}"
        # Avoid huge duplicate tracebacks if logging handlers are duplicated; emit once.
        logger.error("[EmailSender] Send failed: %s", last_exc, exc_info=True)
        return state

    sent_at = datetime.now(timezone.utc).isoformat()
    # from_addr = who is SENDING (us/Gmail OAuth user)
    # to_addr = who is RECEIVING (candidate)
    from_addr = gmail_sender_email or RECRUITER_EMAIL
    to_addr = state.get("from_addr", "")  # Candidate's email
    sender_name = RECRUITER_NAME
    
    # DEBUG: Log what will be saved
    logger.info(f"[EmailSender] DEBUG - Saving reply with from_addr='{from_addr}'")
    logger.info(f"[EmailSender] DEBUG - Saving reply with sender_name='{sender_name}'")
    
    di = state.get("detected_intents")
    if not isinstance(di, list):
        di = []

    reply_record = {
        "email_id": state["email_id"],
        "thread_id": state.get("thread_id", ""),
        "from_addr": from_addr,  # Our Gmail email (sender)
        "to_addr": to_addr,  # Candidate's email (receiver)
        "subject": subject,
        "body": body,  # Our reply body (the generated response)
        "html_body": draft_html_body,
        "sent_at": sent_at,
        "intent_label": state.get("intent_label", ""),
        "profile_type": state.get("profile_type", ""),
        "sender_name": sender_name,
        "detected_intents": di,
    }

    try:
        save_reply(reply_record)
    except Exception as exc:
        logger.warning("[EmailSender] Email sent but archive write failed: %s", exc)

    # IMPORTANT: Treat email/draft as "processed" for the inbound email.
    # We update the DB status here (in addition to the graph finalize step) so that
    # even if later nodes/logging fail or the process is interrupted, we won't
    # reprocess the same inbound email.
    try:
        update_email_status(state["email_id"], "processed")
    except Exception as exc:
        # Avoid failing the pipeline after successfully sending/drafting.
        action = "sent" if SEND_EMAILS_DIRECTLY else "drafted"
        logger.warning(f"[EmailSender] Email {action} but status update failed: %s", exc)

    state["sent"] = True
    state["sent_at"] = sent_at
    if draft_id:
        state["draft_id"] = draft_id
    state["error"] = None

    action = "sent" if SEND_EMAILS_DIRECTLY else "drafted"
    logger.info(
        f"[EmailSender] Email {action} via {send_method} and archived | "
        f"to={reply_record['to_addr']}" + (f" | draft_id={draft_id}" if draft_id else "")
    )
    
    return state