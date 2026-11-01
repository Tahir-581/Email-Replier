SYSTEM = """
You are summarising a prior email thread between a recruiter and a candidate for Acme Corp.

Write a factual summary of 2 to 4 sentences only. Cover:
- What the candidate said
- What was already shared (forms, links, policy info)
- Where the conversation ended

Rules:
- Do NOT add opinions or suggestions
- Do NOT repeat information that is not in the thread
- Do NOT add any greetings or sign-offs
- Output plain text only, no JSON, no markdown
""".strip()


def build_user_prompt(history_records: list[dict]) -> str:
    lines = []
    for i, record in enumerate(history_records, 1):
        lines.append(f"--- Exchange {i} ---")
        lines.append(f"From: {record.get('from_addr', '')}")
        lines.append(f"Subject: {record.get('subject', '')}")
        lines.append(f"Body: {record.get('body', '')}")
        lines.append("")
    return "\n".join(lines).strip()