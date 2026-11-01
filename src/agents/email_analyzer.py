import json
import logging

from src.llm.client import llm
from src.pipeline.state import EmailState
from src.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


SYSTEM = """You are an expert email analyst for a recruiting automation system.

You will be given an inbound email plus optional thread history context.
Your job is to deeply understand the email and output a SINGLE JSON object with the exact schema below.

TASKS:
1) Identify the candidate's name (from body, signature, or email address). If unknown, use an empty string.
2) Summarize what the candidate is saying in plain English (2-3 sentences).
3) List every distinct concern, question, or statement the candidate makes as a numbered list internally, then output them as an array of strings.
4) Identify their current job situation and profile type.
5) Detect if forms were already shared in the thread history (yes/no).

PROFILE TYPE (must be exactly one):
- ai_ml_fit
- senior_ai_ml_fit
- full_stack_fit
- student
- remote_only
- out_of_country
- referrer
- unknown

OUTPUT FORMAT (JSON only, no markdown, no extra keys):
{
  "candidate_name": "string",
  "email_summary": "string (2-3 sentences)",
  "detected_concerns": ["concern 1", "concern 2", "..."],
  "profile_type": "ai_ml_fit | senior_ai_ml_fit | full_stack_fit | student | remote_only | out_of_country | referrer | unknown",
  "forms_already_shared": true | false,
  "concern_count": integer
}

CONSTRAINTS:
- Return ONLY valid JSON.
- concern_count must equal the length of detected_concerns.
- If you are uncertain, choose conservative defaults: empty strings, empty lists, profile_type="unknown", forms_already_shared=false.
"""


def _build_user_prompt(
    *,
    from_addr: str,
    subject: str,
    body: str,
    history_summary: str | None,
    history_records: list[dict] | None,
) -> str:
    history_records = history_records or []
    history_json = json.dumps(history_records[:10], ensure_ascii=False)
    return (
        "INBOUND EMAIL\n"
        f"From: {from_addr}\n"
        f"Subject: {subject}\n"
        f"Body:\n{body}\n\n"
        "THREAD HISTORY CONTEXT\n"
        f"History summary (may be null): {history_summary}\n"
        f"History records (up to 10, JSON): {history_json}\n"
    )


def email_analyzer(state: EmailState) -> EmailState:
    """
    Agent — Email Analyzer.
    Runs before the intent classifier. Produces a structured analysis for downstream agents.
    Sets: candidate_name, email_summary, detected_concerns, forms_already_shared, concern_count, profile_type
    """
    logger.info(f"[EmailAnalyzer] email_id={state.get('email_id')}")

    user_msg = _build_user_prompt(
        from_addr=state.get("from_addr", ""),
        subject=state.get("subject", ""),
        body=state.get("body", ""),
        history_summary=state.get("history_summary"),
        history_records=state.get("history_records"),
    )

    raw = llm.system_user(system=SYSTEM, user=user_msg)

    try:
        data = parse_llm_json(raw)
        candidate_name = (data.get("candidate_name") or "").strip()
        email_summary = (data.get("email_summary") or "").strip()
        detected_concerns = data.get("detected_concerns") or []
        if not isinstance(detected_concerns, list):
            detected_concerns = []
        detected_concerns = [str(x).strip() for x in detected_concerns if str(x).strip()]

        forms_already_shared = bool(data.get("forms_already_shared", False))

        profile_type = (data.get("profile_type") or "unknown").strip()
        allowed = {
            "ai_ml_fit",
            "senior_ai_ml_fit",
            "full_stack_fit",
            "student",
            "remote_only",
            "out_of_country",
            "referrer",
            "unknown",
        }
        if profile_type not in allowed:
            profile_type = "unknown"

        concern_count = len(detected_concerns)

        state["candidate_name"] = candidate_name
        state["email_summary"] = email_summary
        state["detected_concerns"] = detected_concerns
        state["forms_already_shared"] = forms_already_shared
        state["concern_count"] = concern_count
        # stored in GraphState already; intent classifier may overwrite later
        state["profile_type"] = profile_type

    except Exception as e:
        logger.warning(f"[EmailAnalyzer] Parse error: {e} | raw={str(raw)[:200]}")
        state["candidate_name"] = ""
        state["email_summary"] = ""
        state["detected_concerns"] = []
        state["forms_already_shared"] = False
        state["concern_count"] = 0
        state["profile_type"] = "unknown"

    logger.info(
        "[EmailAnalyzer] candidate=%s | concerns=%s | forms_shared=%s | profile=%s",
        state.get("candidate_name", ""),
        state.get("concern_count", 0),
        state.get("forms_already_shared", False),
        state.get("profile_type", "unknown"),
    )
    return state

