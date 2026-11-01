"""
Generate JSON pairing each received (input) email with the system's reply.

Runs the reply pipeline in dry-run mode (no Gmail send, no DB writes).

Usage (from repo root):
    python scripts/generate_replies_json.py "Email 1_ (1).docx"
    python scripts/generate_replies_json.py emails.json -o data/test_results/replies.json
    python scripts/generate_replies_json.py received.txt --candidate-name "Jane Doe"

Supported input formats:
  - .docx  — EMAIL#N or Email N: sections (RESPONSE/Response blocks ignored for generation)
  - .json  — list of emails, or {"emails": [...]}; each item needs "body" (or "incoming_body")
  - .txt   — EMAIL#N sections, blocks separated by ---, or a single email as the whole file
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.replay_qa_docx_emails import (  # noqa: E402
    _EMAIL_HEADER_RE,
    _RESPONSE_HEADER_RE,
    _default_subject,
    parse_qa_docx,
    run_live_pipeline,
    run_reply_pipeline,
)

logger = logging.getLogger(__name__)


def _parse_txt_emails(text: str) -> list[dict[str, Any]]:
    """Parse plain-text files: EMAIL#N blocks, --- separators, or one email."""
    lines = text.splitlines()
    if any(_EMAIL_HEADER_RE.match(line.strip()) for line in lines):
        cases: list[dict[str, Any]] = []
        current_id: int | None = None
        body_lines: list[str] = []
        mode: str | None = None

        def flush() -> None:
            nonlocal current_id, body_lines, mode
            if current_id is None:
                return
            cases.append(
                {
                    "id": current_id,
                    "body": "\n".join(body_lines).strip(),
                }
            )
            body_lines = []
            mode = None

        for line in lines:
            stripped = line.strip()
            header = _EMAIL_HEADER_RE.match(stripped)
            if header:
                flush()
                current_id = int(header.group(1))
                body_lines = []
                mode = "incoming"
                continue
            if _RESPONSE_HEADER_RE.match(stripped):
                mode = "response"
                continue
            if current_id is None:
                continue
            if mode == "incoming":
                body_lines.append(line.rstrip("\n"))
            # ignore RESPONSE section lines

        flush()
        cases.sort(key=lambda item: item["id"])
        return cases

    stripped = text.strip()
    if not stripped:
        return []

    if "\n---\n" in stripped or "\n---\r\n" in stripped:
        parts = re.split(r"\n---+\n", stripped)
        return [{"id": idx, "body": part.strip()} for idx, part in enumerate(parts, start=1) if part.strip()]

    return [{"id": 1, "body": stripped}]


def _parse_json_emails(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        if "emails" in data:
            items = data["emails"]
        elif "results" in data:
            items = data["results"]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("JSON root must be a list or an object with an 'emails' array")

    emails: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Email entry #{idx} must be a JSON object")
        body = (item.get("body") or item.get("incoming_body") or item.get("text") or "").strip()
        if not body:
            raise ValueError(f"Email entry #{idx} is missing 'body' (or 'incoming_body')")
        emails.append(
            {
                "id": item.get("id", idx),
                "body": body,
                "subject": item.get("subject"),
                "from_addr": item.get("from_addr"),
                "candidate_name": item.get("candidate_name"),
            }
        )
    return emails


def load_emails(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        cases = parse_qa_docx(path)
        return [
            {
                "id": case["id"],
                "body": case["incoming_body"],
                "subject": None,
            }
            for case in cases
        ]
    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _parse_json_emails(raw)
    if suffix in {".txt", ".text"}:
        return _parse_txt_emails(path.read_text(encoding="utf-8"))
    raise SystemExit(
        f"Unsupported input format '{suffix}'. Use .docx, .json, or .txt"
    )


def build_pipeline_state(
    email: dict[str, Any],
    *,
    candidate_name: str,
    from_addr: str,
) -> dict[str, Any]:
    case_id = int(email.get("id") or 1)
    body = email["body"]
    ts = datetime.now(timezone.utc).isoformat()
    subject = email.get("subject") or _default_subject(case_id, body)
    return {
        "email_id": f"batch_reply_{case_id:04d}",
        "message_id": f"batch_reply_msg_{case_id:04d}",
        "thread_id": f"batch_reply_thread_{case_id:04d}",
        "subject": subject,
        "from_addr": email.get("from_addr") or from_addr,
        "to_addr": "recruiter@example.com",
        "body": body,
        "received_at": ts,
        "status": "pending",
        "candidate_name": email.get("candidate_name") or candidate_name,
        "forms_already_shared": bool(email.get("forms_already_shared")),
        "history_records": email.get("history_records") or [],
        "history_summary": email.get("history_summary"),
    }


def generate_reply_record(
    email: dict[str, Any],
    *,
    candidate_name: str,
    from_addr: str,
    live: bool = False,
) -> dict[str, Any]:
    case_id = email.get("id")
    input_email = {
        "id": case_id,
        "subject": email.get("subject") or _default_subject(int(case_id or 1), email["body"]),
        "body": email["body"],
        "from_addr": email.get("from_addr") or from_addr,
        "candidate_name": email.get("candidate_name") or candidate_name,
    }

    try:
        state = build_pipeline_state(
            email,
            candidate_name=candidate_name,
            from_addr=from_addr,
        )
        result = run_live_pipeline(state) if live else run_reply_pipeline(state)

        if not result.get("is_relevant", True):
            return {
                **input_email,
                "input_email": input_email,
                "generated_email": None,
                "status": "irrelevant",
                "irrelevant_reason": result.get("irrelevant_reason"),
            }

        generated_email = {
            "subject": result.get("reply_subject", ""),
            "body": result.get("reply_body", ""),
        }
        return {
            **input_email,
            "input_email": input_email,
            "generated_email": generated_email,
            "status": result.get("pipeline_stopped", "completed"),
            "detected_intents": result.get("detected_intents"),
        }
    except Exception as exc:
        logger.exception("Failed to generate reply for id=%s", case_id)
        return {
            **input_email,
            "input_email": input_email,
            "generated_email": None,
            "status": "error",
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate replies for received emails and write input/output pairs to JSON.",
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to received emails (.docx, .json, or .txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/test_results/<input_stem>_replies_<timestamp>.json)",
    )
    parser.add_argument(
        "--candidate-name",
        default="Alex Candidate",
        help="Default candidate name for the email writer",
    )
    parser.add_argument(
        "--from-addr",
        default="candidate@example.com",
        help="Default From address when not set in the input file",
    )
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated email ids to process (e.g. 1,3,5). Default: all.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Persist to PostgreSQL (seed email, history, reply); no Gmail send",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    input_path = args.input_file.resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    emails = load_emails(input_path)
    if not emails:
        raise SystemExit(f"No emails found in {input_path}")

    if args.only.strip():
        wanted = {int(part.strip()) for part in args.only.split(",") if part.strip()}
        emails = [email for email in emails if int(email.get("id") or 0) in wanted]
        if not emails:
            raise SystemExit(f"No matching ids in --only: {sorted(wanted)}")

    logger.info("Loaded %s email(s) from %s", len(emails), input_path.name)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_out = PROJECT_ROOT / "data" / "test_results" / f"{input_path.stem}_replies_{ts}.json"
    output_path = (args.output or default_out).resolve()

    results: list[dict[str, Any]] = []
    for email in emails:
        logger.info("Generating reply for id=%s ...", email.get("id"))
        record = generate_reply_record(
            email,
            candidate_name=args.candidate_name,
            from_addr=args.from_addr,
            live=args.live,
        )
        results.append(
            {
                "id": record.get("id"),
                "input_email": record["input_email"],
                "generated_email": record.get("generated_email"),
                "status": record.get("status"),
                "irrelevant_reason": record.get("irrelevant_reason"),
                "error": record.get("error"),
                "detected_intents": record.get("detected_intents"),
            }
        )
        preview = (
            (record.get("generated_email") or {}).get("body")
            or record.get("error")
            or record.get("irrelevant_reason")
            or ""
        )[:120]
        logger.info("  -> %s", str(preview).replace("\n", " "))

    payload = {
        "source": str(input_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(results),
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\nProcessed {len(results)} email(s) from: {input_path}")
    print(f"Output JSON: {output_path}")


if __name__ == "__main__":
    main()
