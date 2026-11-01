import logging
from src.pipeline.state import EmailState

logger = logging.getLogger(__name__)


def status_updater(state: EmailState) -> EmailState:
    """
    Agent 9 — Status Updater.
    Final node. Logs the completed pipeline run summary.
    """
    logger.info(
        f"[StatusUpdater] DONE | email_id={state.get('email_id')} | "
        f"intent={state.get('intent_id')} ({state.get('intent_label')}) | "
        f"profile={state.get('profile_type')} | "
        f"sent={state.get('sent')} | "
        f"status={state.get('status')}"
    )
    return state
