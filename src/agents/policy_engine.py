import logging

from src.llm.client import llm
from src.llm.prompts import policy_engine as prompt
from src.pipeline.state import EmailState
from src.utils.reply_constraints import derive_reply_constraints, format_constraints

logger = logging.getLogger(__name__)


def _forms_already_shared(history_records: list[dict]) -> bool:
    for record in history_records:
        body = record.get("body", "")
        if "forms.gle" in body or "docs.google.com/forms" in body:
            return True
    return False


def policy_engine(state: EmailState) -> EmailState:
    """
    Agent 4, Policy Engine.
    Maps detected intents + email context -> detailed writing instructions.
    Sets: policy_prompt, reply_constraints
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

    logger.info(
        "[PolicyEngine] email_id=%s | intents=%s | profile=%s",
        state.get("email_id"),
        [d.get("intent_id") for d in detected_intents],
        state.get("profile_type"),
    )

    forms_shared = bool(state.get("forms_already_shared")) or _forms_already_shared(
        state.get("history_records", [])
    )
    state["forms_already_shared"] = forms_shared

    constraints = derive_reply_constraints({**state, "detected_intents": detected_intents})
    constraints_text = format_constraints(constraints)
    state["reply_constraints"] = constraints

    user_msg = prompt.build_user_prompt(
        detected_intents=detected_intents,
        profile_type=state.get("profile_type", ""),
        subject=state.get("subject", ""),
        body=state.get("body", ""),
        history_summary=state.get("history_summary"),
        detected_concerns=state.get("detected_concerns") or [],
        email_summary=state.get("email_summary"),
        constraints_text=constraints_text,
        forms_already_shared=forms_shared,
    )

    policy = llm.system_user(system=prompt.SYSTEM, user=user_msg)
    state["policy_prompt"] = policy.strip()

    logger.info("[PolicyEngine] Policy generated (%s chars).", len(policy))
    return state
