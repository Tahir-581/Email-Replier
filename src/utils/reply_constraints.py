from __future__ import annotations

import re
from typing import Any

from src.utils.config import FORM_URLS, LINKEDIN_URL


LINKEDIN_TOUCHPOINT_SENTENCE = (
    "Feel free to connect with me on LinkedIn for future touchpoints."
)
_DEFAULT_LINKEDIN_URL = "https://www.linkedin.com/in/your-recruiter-profile/"
_LINKEDIN_TOUCHPOINT_RE = re.compile(
    r"linkedin.*(?:touchpoint|connect with me|future touchpoint)"
    r"|(?:touchpoint|connect with me|future touchpoint).*linkedin",
    re.IGNORECASE | re.DOTALL,
)


NO_FORM_INTENTS = {19, 20, 21, 22, 23, 25, 27, 28}
COMPANY_INFO_INTENTS = {11, 15}
LINKEDIN_TOUCHPOINT_INTENTS = {1, 7, 10, 16}
DECLINE_STYLE_INTENTS = {1}


def _normalize_text(*parts: str | None) -> str:
    return "\n".join((part or "") for part in parts).lower()


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _mentions_ai_ml(text: str) -> bool:
    return _has_any(text, ("ai/ml", "ai ml", "machine learning", "ml engineer", "artificial intelligence", "data science", "deep learning"))


def _mentions_frontend_stack(text: str) -> bool:
    return _has_any(text, ("frontend", "front end", "full stack", "mern", ".net", "flutter", "react", "angular", "mobile developer"))


def _mentions_unsupported_role(text: str) -> bool:
    return _has_any(text, ("hr manager", "content writer", "graphic designer", "designer role", "writer role"))


def recruiter_linkedin_url() -> str:
    url = (LINKEDIN_URL or _DEFAULT_LINKEDIN_URL).strip()
    return url.rstrip("/")


def mentions_linkedin_touchpoint(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    if LINKEDIN_TOUCHPOINT_SENTENCE.lower() in normalized.lower():
        return True
    return bool(_LINKEDIN_TOUCHPOINT_RE.search(normalized))


def _linkedin_url_in_text(text: str, linkedin_url: str) -> bool:
    if not linkedin_url:
        return False
    haystack = (text or "").lower()
    needle = linkedin_url.lower().rstrip("/")
    return needle in haystack or f"{needle}/" in haystack


def ensure_linkedin_url_on_touchpoint(body: str, *, linkedin_url: str | None = None) -> str:
    """Append the recruiter LinkedIn profile URL when a touchpoint invite is present."""
    text = (body or "").rstrip()
    if not text or not mentions_linkedin_touchpoint(text):
        return body or ""

    url = (linkedin_url or recruiter_linkedin_url()).strip().rstrip("/")
    if not url or _linkedin_url_in_text(text, url):
        return body or ""

    return f"{text}\n{url}/"


def _format_form_line(form_key: str) -> str:
    labels = {
        "senior_ai_ml": "Senior AI/ML Engineer",
        "ai_ml": "AI/ML Engineer",
        "full_stack": "Full Stack Developer",
        "ai_internship": "AI Internship",
    }
    return f"- {labels[form_key]}: {FORM_URLS[form_key]}"


def derive_reply_constraints(state: dict[str, Any]) -> dict[str, Any]:
    intents = {int(item.get("intent_id")) for item in (state.get("detected_intents") or []) if item.get("intent_id") is not None}
    body = state.get("body", "") or ""
    summary = state.get("email_summary", "") or ""
    concerns = " ".join(state.get("detected_concerns") or [])
    text = _normalize_text(body, summary, concerns)
    forms_already_shared = bool(state.get("forms_already_shared"))

    company_intro_allowed = bool(intents & COMPANY_INFO_INTENTS)
    linkedin_allowed = bool(intents & LINKEDIN_TOUCHPOINT_INTENTS)

    prohibited_phrases = [
        'Avoid generic acknowledgements such as "I completely understand" unless the email genuinely warrants it.',
        'Never say "I respect your decision", "I respect your decision to decline", or any variation of that phrase in any scenario.',
        'Do not add "in case things change" unless the candidate is actually declining and a future touchpoint is appropriate.',
        'Do not invent the candidate\'s background, current status, internship completion, selection, or internal review outcome.',
    ]

    priority = []
    if state.get("detected_concerns"):
        priority.append(f"Answer this first: {state['detected_concerns'][0]}")
    priority.append("Keep the reply short, direct, and human.")

    forms_to_share: list[str] = []
    forms_reason = "No forms unless they help answer the actual request."

    if intents & NO_FORM_INTENTS:
        forms_reason = "Do not include job forms for this scenario unless another detected intent clearly requires a next-step application link."

    if 24 in intents or _mentions_unsupported_role(text):
        forms_reason = "No matching supported form exists for the asked role. Ask for CV/portfolio or suggest waiting for a relevant opening."
    elif 25 in intents or 21 in intents or 23 in intents or 22 in intents or 20 in intents:
        forms_reason = "Do not include any job forms in this reply."
    elif 28 in intents:
        forms_reason = "Acknowledge receipt and review only. Do not include job forms."
    elif 13 in intents:
        forms_to_share = ["ai_internship"]
        forms_reason = "Share only the AI Internship form. Mention AI/ML full-time forms only if explicitly useful as reference and add context first."
    elif 16 in intents:
        if 19 in intents:
            forms_reason = "Complaint with follow-up: LinkedIn touchpoint allowed; defer job forms while addressing the communication concern."
        elif _mentions_frontend_stack(text):
            forms_to_share = ["full_stack"]
            forms_reason = "Complaint with disengagement: share only the relevant role form for soft re-engagement."
        elif 13 in intents or _has_any(text, ("internship", "intern ")):
            forms_to_share = ["ai_internship"]
            forms_reason = "Complaint with disengagement: share only the relevant role form for soft re-engagement."
        elif _mentions_ai_ml(text) or state.get("profile_type") in {"ai_ml_fit", "senior_ai_ml_fit"}:
            forms_to_share = ["senior_ai_ml", "ai_ml"]
            forms_reason = "Complaint with disengagement: share only the relevant role form for soft re-engagement."
        else:
            forms_to_share = ["senior_ai_ml", "ai_ml"]
            forms_reason = "Complaint with disengagement: share only the relevant role form for soft re-engagement."
    elif 8 in intents or _mentions_frontend_stack(text):
        forms_to_share = ["full_stack"]
        forms_reason = "Share only the Full Stack Developer form for Frontend / Full Stack inquiries."
    elif 9 in intents or 10 in intents:
        if _mentions_frontend_stack(text):
            forms_to_share = ["full_stack"]
        elif 13 in intents:
            forms_to_share = ["ai_internship"]
        else:
            forms_to_share = ["senior_ai_ml", "ai_ml"]
        forms_reason = "Share only the forms relevant to the role being referred or shared."
    elif 26 in intents:
        if _mentions_frontend_stack(text):
            forms_to_share = ["full_stack"]
        elif 13 in intents:
            forms_to_share = ["ai_internship"]
        elif _mentions_ai_ml(text) or state.get("profile_type") in {"ai_ml_fit", "senior_ai_ml_fit"}:
            forms_to_share = ["senior_ai_ml", "ai_ml"]
        forms_reason = "Apologize for the form issue and provide only the correct alternative relevant form."
    elif 2 in intents:
        if _mentions_frontend_stack(text):
            forms_to_share = ["full_stack"]
        elif _mentions_ai_ml(text) or state.get("profile_type") in {"ai_ml_fit", "senior_ai_ml_fit"}:
            forms_to_share = ["senior_ai_ml", "ai_ml"]
        forms_reason = "Use only the forms relevant to the role the candidate is asking about."

    if forms_already_shared and forms_to_share:
        forms_reason += " Forms were already shared in the thread, so avoid resharing unless the link directly moves the action forward."

    return {
        "company_intro_allowed": company_intro_allowed,
        "linkedin_allowed": linkedin_allowed,
        "forms_already_shared": forms_already_shared,
        "forms_to_share": forms_to_share,
        "forms_reason": forms_reason,
        "form_lines": [_format_form_line(key) for key in forms_to_share],
        "priority": priority,
        "prohibited_phrases": prohibited_phrases,
    }


def format_constraints(constraints: dict[str, Any]) -> str:
    lines = ["Reply constraints:"]
    lines.append(f"- Company intro allowed: {'yes' if constraints.get('company_intro_allowed') else 'no'}")
    lines.append(f"- LinkedIn allowed: {'yes' if constraints.get('linkedin_allowed') else 'no'}")
    if constraints.get("linkedin_allowed"):
        lines.append(f"- LinkedIn touchpoint line (use exactly): {LINKEDIN_TOUCHPOINT_SENTENCE}")
        lines.append(f"- LinkedIn profile URL (include on the next line): {recruiter_linkedin_url()}/")
    lines.append(f"- Forms already shared: {'yes' if constraints.get('forms_already_shared') else 'no'}")
    lines.append(f"- Form rule: {constraints.get('forms_reason', '').strip()}")

    form_lines = constraints.get("form_lines") or []
    if form_lines:
        lines.append("- Allowed forms:")
        lines.extend(form_lines)
    else:
        lines.append("- Allowed forms: none by default")

    for item in constraints.get("priority") or []:
        lines.append(f"- Priority: {item}")
    for item in constraints.get("prohibited_phrases") or []:
        lines.append(f"- Guardrail: {item}")
    return "\n".join(lines)
