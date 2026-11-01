import logging

from src.db.session import get_history, save_history
from src.llm.client import llm
from src.llm.prompts import history_summary as prompt
from src.pipeline.state import EmailState

logger = logging.getLogger(__name__)


def history_checker(state: EmailState) -> EmailState:
    """
    Agent 2 — History Checker.
    Checks if this email_id has been seen before.
    If history exists, generates a summary.
    Sets: history_records, history_summary
    """
    email_id = state["email_id"]
    logger.info(f"[HistoryChecker] email_id={email_id}")

    records = get_history(email_id)
    state["history_records"] = records

    if not records:
        logger.info(f"[HistoryChecker] No prior history found.")
        state["history_summary"] = None
    else:
        logger.info(f"[HistoryChecker] Found {len(records)} history record(s). Summarising.")
        user_msg = prompt.build_user_prompt(records)
        summary  = llm.system_user(system=prompt.SYSTEM, user=user_msg)
        state["history_summary"] = summary.strip()
        logger.info(f"[HistoryChecker] Summary generated ({len(summary)} chars).")

    # Record this email into history so future runs can reference it
    save_history({
        "email_id":    email_id,
        "thread_id":   state.get("thread_id", ""),
        "from_addr":   state.get("from_addr", ""),
        "to_addr":     state.get("to_addr", ""),
        "subject":     state.get("subject", ""),
        "body":        state.get("body", ""),
        "received_at": state.get("received_at", ""),
    })

    return state
