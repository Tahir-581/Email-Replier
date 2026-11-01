"""
scripts/test_multi_intent.py

End-to-end multi-intent smoke test:
- Builds a sample email containing multiple concerns.
- Invokes the LangGraph pipeline with a minimal state.
- Prints key outputs, including deterministic reply constraints.
- Saves results to data/test_results/multi_intent_test_{timestamp}.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.graph import pipeline


def _results_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "test_results"


def main() -> None:
    body = """
Hi,

I am interested in the AI/ML role, but I need a few clarifications first:
1) Is there any remote or hybrid option?
2) If not, how does relocation work, and is accommodation managed by the company?
3) I also wanted to understand the salary policy before moving forward.
4) If I decide to proceed, what does the interview process look like?

Best regards,
Ahmed
""".strip()

    state = {
        "email_id": "test_email_multi_intent_001",
        "message_id": "test_message_multi_intent_001",
        "thread_id": "test_thread_multi_intent_001",
        "subject": "AI/ML Engineer role questions",
        "from_addr": "ahmed.test@example.com",
        "to_addr": "recruiter@example.com",
        "body": body,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }

    result = pipeline.invoke(state)

    print("\n=== MULTI-INTENT TEST OUTPUT ===")
    print("email_summary:", result.get("email_summary"))
    print("detected_concerns:", result.get("detected_concerns"))
    print("detected_intents:", result.get("detected_intents"))
    print("reply_constraints:", result.get("reply_constraints"))
    print("reply_body:", result.get("reply_body"))

    out_dir = _results_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"multi_intent_test_{ts}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved results to: {out_path}")


if __name__ == "__main__":
    main()
