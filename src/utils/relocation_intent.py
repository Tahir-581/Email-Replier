"""
Heuristics for relocation-related wording in recruiting replies.

The pair-wise intent classifier can mislabel short replies: e.g. "happy to relocate"
may match intent 1 (not interested) because bucket 1 mentions "happy in current role".
This module corrects that failure mode using deterministic phrase checks.
"""

from __future__ import annotations

# Checked first: refusal / inability to relocate
_NEGATIVE_RELOC_SUBSTRINGS = (
    "not willing to relocat",
    "not happy to relocat",
    "not open to relocat",
    "won't relocat",
    "wont relocat",
    "can't relocat",
    "cannot relocat",
    "unable to relocat",
    "don't want to relocat",
    "do not want to relocat",
    "not interested in relocat",
    "no plans to relocat",
    "not relocating",
    "not able to relocat",
)

# Willingness / openness to relocate (substring match on "relocat" covers relocate/relocating)
_POSITIVE_RELOC_SUBSTRINGS = (
    "happy to relocat",
    "glad to relocat",
    "willing to relocat",
    "willing to move",
    "open to relocat",
    "fine with relocat",
    "okay to relocat",
    "ok to relocat",
    "can relocat",
    "ready to relocat",
    "comfortable relocat",
    "no problem relocat",
    "available for relocat",
    "available to relocat",
    "happy to move",
)


def _combined_text(body: str, concerns: list[str] | None, email_summary: str | None) -> str:
    parts = [body or "", email_summary or ""]
    if concerns:
        parts.append(" ".join(concerns))
    return "\n".join(parts)


def relocation_sentiment(text: str) -> str | None:
    """
    Return 'positive' if the candidate affirms willingness to relocate,
    'negative' if they refuse or cannot, or None if relocation is not clearly expressed.
    Negative signals take precedence over positive (e.g. "not happy to relocate").
    """
    t = text.lower()
    for n in _NEGATIVE_RELOC_SUBSTRINGS:
        if n in t:
            return "negative"
    for p in _POSITIVE_RELOC_SUBSTRINGS:
        if p in t:
            return "positive"
    return None


def strip_false_not_interested_for_positive_relocation(
    matched_ids: list[int],
    *,
    body: str,
    concerns: list[str] | None = None,
    email_summary: str | None = None,
) -> list[int]:
    """
    If intent 1 was matched but the message clearly affirms willingness to relocate,
    drop intent 1. Default replacement is intent 2 (interested / next steps, forms).
    """
    if 1 not in matched_ids:
        return list(matched_ids)
    text = _combined_text(body, concerns, email_summary)
    if relocation_sentiment(text) != "positive":
        return list(matched_ids)
    out = [i for i in matched_ids if i != 1]
    if not out:
        out = [2]
    return out
