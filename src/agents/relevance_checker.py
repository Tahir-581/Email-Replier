import logging

from src.llm.client import llm
from src.llm.prompts import is_relevant as prompt
from src.pipeline.state import EmailState
from src.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


def relevance_checker(state: EmailState) -> EmailState:
    """
    Agent 1 — Relevance Checker.
    Decides whether the email is relevant to recruiting.
    Sets: is_relevant, irrelevant_reason
    """
    logger.info(f"[RelevanceChecker] email_id={state['email_id']}")

    user_msg = prompt.build_user_prompt(
        subject=state.get("subject", ""),
        body=state.get("body", ""),
    )

    raw = llm.system_user(system=prompt.SYSTEM, user=user_msg)

    try:
        data = parse_llm_json(raw)
        state["is_relevant"]       = bool(data.get("is_relevant", False))
        state["irrelevant_reason"] = data.get("reason", "")
    except Exception as e:
        logger.warning(f"[RelevanceChecker] JSON parse failed: {e} | raw={raw[:200]}")
        state["is_relevant"]       = False
        state["irrelevant_reason"] = "Failed to parse LLM response"

    logger.info(
        f"[RelevanceChecker] is_relevant={state['is_relevant']} | "
        f"reason={state.get('irrelevant_reason', '')}"
    )
    return state