import logging

from src.llm.client import llm
from src.llm.prompts import email_writer as prompt
from src.pipeline.state import EmailState
from src.utils.json_parser import parse_llm_json
from src.utils.reply_constraints import ensure_linkedin_url_on_touchpoint, format_constraints

logger = logging.getLogger(__name__)


def email_writer(state: EmailState) -> EmailState:
    """
    Agent 5, Email Writer.
    Writes the reply email using the consolidated policy prompt, detected intents,
    detected concerns, and deterministic reply constraints.
    Sets: reply_subject, reply_body
    """
    detected_intents = state.get("detected_intents") or []
    if not isinstance(detected_intents, list):
        detected_intents = []
    if not detected_intents:
        primary_id = state.get("primary_intent_id") or state.get("intent_id")
        primary_label = state.get("primary_intent_label") or state.get("intent_label")
        if primary_id is not None:
            detected_intents = [
                {"intent_id": primary_id, "intent_label": primary_label or "Unknown"}
            ]

    detected_concerns = state.get("detected_concerns") or []
    if not isinstance(detected_concerns, list):
        detected_concerns = []

    logger.info(
        "[EmailWriter] email_id=%s | intents=%s | concerns=%s",
        state.get("email_id"),
        [d.get("intent_id") for d in detected_intents],
        len(detected_concerns),
    )

    constraints_text = format_constraints(state.get("reply_constraints") or {})

    user_msg = prompt.build_user_prompt(
        detected_intents=detected_intents,
        candidate_name=state.get("candidate_name", "") or "",
        email_summary=state.get("email_summary", "") or "",
        detected_concerns=detected_concerns,
        candidate_email=state.get("body", "") or "",
        original_subject=state.get("subject", "") or "",
        from_addr=state.get("from_addr", "") or "",
        policy_prompt=state.get("policy_prompt", "") or "",
        constraints_text=constraints_text,
    )

    raw = llm.system_user(system=prompt.SYSTEM, user=user_msg)

    try:
        data = parse_llm_json(raw)
        state["reply_subject"] = data.get("subject", f"Re: {state.get('subject', '')}")
        state["reply_body"] = data.get("body", "")
    except Exception as e:
        logger.warning("[EmailWriter] JSON parse failed: %s | using raw as body.", e)
        state["reply_subject"] = f"Re: {state.get('subject', '')}"
        state["reply_body"] = raw.strip()

    state["reply_body"] = ensure_linkedin_url_on_touchpoint(state.get("reply_body", ""))

    logger.info(
        "[EmailWriter] Reply written | subject='%s' | body_len=%s",
        state["reply_subject"],
        len(state["reply_body"]),
    )
    return state
