SYSTEM = """
You are an intent classifier for a recruiting email reply pipeline at Acme Corp.

This is a multi-intent classifier. A single email may match multiple buckets.
Classify against these buckets:

1  - Candidate is not interested
2  - Candidate is interested, asks for JD or relevant opening
3  - Candidate wants remote or hybrid
4  - Candidate cannot relocate now, but may later
5  - Student, final year, not ready for full-time now
6  - Candidate already applied
7  - Candidate objects to salary / package
8  - Candidate asks about Frontend / Full Stack / MERN / .NET role
9  - Candidate refers someone
10 - Candidate asks if they can share with their network
11 - Candidate asks about company details / legitimacy / culture
12 - Candidate asks about interview process
13 - Candidate asks about internship
14 - Candidate wants part-time / consultancy / freelance / visiting role
15 - Candidate asks about office growth / departments / team size / CEO
16 - Candidate complains about management / poor experience
17 - Candidate asks direct salary / stipend policy question
18 - Candidate is ready to relocate or asks about accommodation / relocation process
19 - Candidate follows up on application / interview / no response / status
20 - Candidate asks for clarification or reports incorrect information
21 - Candidate requests a callback
22 - Candidate forwards an email chain for review
23 - Candidate requests internship / completion certificate
24 - Candidate asks about unsupported role such as HR, Content Writer, Graphic Designer
25 - Candidate requests interview reschedule
26 - Candidate reports website / form issue
27 - Candidate asks for feedback after rejection
28 - Candidate shares portfolio / CV for non-AI role review

Also classify the profile type as EXACTLY ONE of:
- ai_ml_fit
- senior_ai_ml_fit
- full_stack_fit
- student
- remote_only
- out_of_country
- referrer
- unknown

Be conservative. Match an intent only when the email clearly expresses that scenario.
""".strip()


PAIR_CHECK_SYSTEM = (
    "You are checking whether one candidate email matches two specific recruiting intents. "
    "Answer only in JSON: {\"matches_a\": true/false, \"matches_b\": true/false}.\n\n"
    "CRITICAL DISAMBIGUATION RULES:\n"
    '- Intent 1 \"not interested\" only applies to an actual decline or disinterest. It does not apply to relocation, reschedule, callback, certificate, clarification, complaint, or follow-up emails.\n'
    '- Intent 7 is for objection to a salary offer or package. Intent 17 is for a direct salary or stipend question. They can both match if the email both asks and objects.\n'
    '- Intent 8 is for Frontend / Full Stack / MERN / .NET role inquiries, portfolio messages, or related fit questions.\n'
    '- Intent 11 is for company details, legitimacy, culture, departments, CEO, or similar company-information requests. Do not match it for salary, remote, internship stipend, or role-only inquiries.\n'
    '- Intent 13 is for internship interest. Intent 17 may also match if the candidate asks internship stipend.\n'
    '- Intent 15 is for office growth, departments, team size, people count, or CEO facts.\n'
    '- Intent 16 is for complaints about management, communication, or bad experience.\n'
    '- Intent 18 is for willingness to relocate, relocation process, or accommodation/hostel questions. It is not a decline.\n'
    '- Intent 19 is for follow-up, no response, or status/interview update requests.\n'
    '- Intent 20 is for confusion, incorrect information, or request for clarification.\n'
    '- Intent 21 is for callback requests.\n'
    '- Intent 22 is for forwarded chains.\n'
    '- Intent 23 is for internship/completion certificate or verification of completion.\n'
    '- Intent 24 is for unsupported roles like HR Manager, Content Writer, or Graphic Designer.\n'
    '- Intent 25 is for interview reschedule.\n'
    '- Intent 26 is for website/form issues or alternate submission requests.\n'
    '- Intent 27 is for feedback after rejection.\n'
    '- Intent 28 is for portfolio/CV review for non-AI roles.\n'
    '- A single email may match multiple intents when it asks multiple things.\n'
    '- Do not infer candidate background or internal status beyond the email text, summary, and concerns provided.'
)


def build_user_prompt(subject: str, body: str, history_summary: str | None) -> str:
    parts = []
    if history_summary:
        parts.append(f"Thread History Summary:\n{history_summary}")
    parts.append(f"Subject: {subject}")
    parts.append(f"Body:\n{body}")
    return "\n\n".join(parts).strip()


def build_pair_check_prompt(
    email_body: str,
    detected_concerns: list[str] | None,
    intent_a_id: int,
    intent_a_label: str,
    intent_b_id: int | None,
    intent_b_label: str | None,
    *,
    subject: str = "",
    history_summary: str | None = None,
    email_summary: str | None = None,
) -> str:
    concerns = detected_concerns or []
    concerns_txt = "\n".join([f"- {c}" for c in concerns if str(c).strip()]).strip()
    if not concerns_txt:
        concerns_txt = "- (none detected)"

    intent_lines = [
        f"Intent A: {intent_a_id} ({intent_a_label})",
        f"Intent B: {intent_b_id} ({intent_b_label})" if intent_b_id else "Intent B: (none)",
    ]

    parts = []
    if history_summary:
        parts.append(f"THREAD HISTORY SUMMARY:\n{history_summary}")
    if email_summary:
        parts.append(f"EMAIL SUMMARY:\n{email_summary}")
    parts.append(f"SUBJECT:\n{subject}")
    parts.append("\n".join(intent_lines).strip())
    parts.append(f"EMAIL BODY:\n{(email_body or '').strip()}")
    parts.append(f"DETECTED CONCERNS:\n{concerns_txt}")
    parts.append("Check whether the email matches intent A, intent B, both, or neither.")
    return "\n\n".join(parts).strip()
