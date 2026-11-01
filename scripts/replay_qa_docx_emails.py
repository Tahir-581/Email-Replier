"""
Replay candidate emails from a QA Word document through the reply pipeline (dry-run).

Reads pairs of incoming email + baseline response from a .docx (e.g. "Email 1_ (1).docx"),
runs each incoming message through relevance → history → analyzer → intent → policy → writer
without sending mail or mutating production DB rows, then writes a report .docx.

Usage (from repo root):
    python scripts/replay_qa_docx_emails.py
    python scripts/replay_qa_docx_emails.py --input "Email 1_ (1).docx" --output data/test_results/qa_replay.docx
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.email_analyzer import email_analyzer
from src.agents.email_writer import email_writer
from src.agents.history_checker import history_checker
from src.agents.intent_classifier import intent_classifier
from src.agents.intent_persister import intent_persister
from src.agents.policy_engine import policy_engine
from src.agents.relevance_checker import relevance_checker
from src.db.session import save_email, save_reply, update_email_status
from src.utils.config import RECRUITER_EMAIL, RECRUITER_NAME

logger = logging.getLogger(__name__)

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# EMAIL#1 (legacy QA) or "Email 1:" / "Email 1" (Word doc format)
_EMAIL_HEADER_RE = re.compile(
    r"^(?:EMAIL#|Email\s+)(\d+)\s*:?\s*$",
    re.IGNORECASE,
)
_RESPONSE_HEADER_RE = re.compile(r"^Response\s*:\s*$", re.IGNORECASE)


def _read_docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for para in root.iter(f"{_W_NS}p"):
        parts: list[str] = []
        for node in para.iter(f"{_W_NS}t"):
            if node.text:
                parts.append(node.text)
            if node.tail:
                parts.append(node.tail)
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return paragraphs


def parse_qa_paragraphs(paragraphs: list[str]) -> list[dict[str, Any]]:
    """
    Parse QA email sections from plain paragraph lines.

    Supports headers: EMAIL#N or Email N: (optional colon).
    Response sections: RESPONSE: or Response : (flexible spacing).

    Returns list of dicts: id, incoming_body, baseline_response.
    """
    cases: list[dict[str, Any]] = []
    current_id: int | None = None
    incoming_lines: list[str] = []
    response_lines: list[str] = []
    mode: str | None = None  # "incoming" | "response"

    def flush() -> None:
        nonlocal current_id, incoming_lines, response_lines, mode
        if current_id is None:
            return
        cases.append(
            {
                "id": current_id,
                "incoming_body": "\n".join(incoming_lines).strip(),
                "baseline_response": "\n".join(response_lines).strip(),
            }
        )
        incoming_lines = []
        response_lines = []
        mode = None

    for line in paragraphs:
        header = _EMAIL_HEADER_RE.match(line)
        if header:
            flush()
            current_id = int(header.group(1))
            incoming_lines = []
            response_lines = []
            mode = "incoming"
            continue

        if _RESPONSE_HEADER_RE.match(line):
            mode = "response"
            continue

        if current_id is None:
            continue

        if mode == "incoming":
            incoming_lines.append(line)
        elif mode == "response":
            response_lines.append(line)

    flush()
    cases.sort(key=lambda item: item["id"])
    return cases


def parse_qa_docx(path: Path) -> list[dict[str, Any]]:
    """Parse EMAIL#N / Email N: sections from a .docx QA document."""
    return parse_qa_paragraphs(_read_docx_paragraphs(path))


def _default_subject(case_id: int, body: str) -> str:
    first_line = body.strip().split("\n", 1)[0].strip()
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."
    return first_line or f"QA replay email #{case_id}"


def _build_initial_state(case: dict[str, Any], *, candidate_name: str, from_addr: str) -> dict[str, Any]:
    case_id = case["id"]
    body = case["incoming_body"]
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "email_id": f"qa_replay_{case_id:03d}",
        "message_id": f"qa_replay_msg_{case_id:03d}",
        "thread_id": f"qa_replay_thread_{case_id:03d}",
        "subject": _default_subject(case_id, body),
        "from_addr": from_addr,
        "to_addr": "recruiter@example.com",
        "body": body,
        "received_at": ts,
        "status": "pending",
        "candidate_name": candidate_name,
        "forms_already_shared": False,
        "history_records": [],
        "history_summary": None,
    }


def run_reply_pipeline(state: dict[str, Any]) -> dict[str, Any]:
    """Run agents through email_writer; no Gmail send or DB status updates."""

    def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    def _empty_history(_email_id: str) -> list[dict[str, Any]]:
        return []

    with (
        patch("src.db.session.update_email_status", _noop),
        patch("src.db.session.save_history", _noop),
        patch("src.db.session.get_history", _empty_history),
        patch("src.db.session.save_reply", _noop),
        patch("src.utils.intent_store.save_intents_to_json", _noop),
    ):
        current = dict(state)
        current = relevance_checker(current)
        if not current.get("is_relevant"):
            current["pipeline_stopped"] = "irrelevant"
            return current

        current = history_checker(current)
        current = email_analyzer(current)
        current = intent_classifier(current)
        current = intent_persister(current)
        current = policy_engine(current)
        current = email_writer(current)
        current["pipeline_stopped"] = "completed"
        return current


def seed_batch_email(state: dict[str, Any]) -> None:
    """Insert the inbound email into PostgreSQL if not already present."""
    save_email(
        {
            "id": state["email_id"],
            "from": state.get("from_addr", ""),
            "to": state.get("to_addr", ""),
            "subject": state.get("subject", ""),
            "body": state.get("body", ""),
            "thread_id": state.get("thread_id", ""),
            "date": state.get("received_at", ""),
        }
    )


def run_live_pipeline(state: dict[str, Any]) -> dict[str, Any]:
    """Run agents with real DB persistence; stop after email_writer (no Gmail)."""
    seed_batch_email(state)
    update_email_status(state["email_id"], "processing")

    current = dict(state)
    current = relevance_checker(current)
    if not current.get("is_relevant"):
        update_email_status(current["email_id"], "irrelevant")
        current["pipeline_stopped"] = "irrelevant"
        return current

    current = history_checker(current)
    current = email_analyzer(current)
    current = intent_classifier(current)
    current = intent_persister(current)
    current = policy_engine(current)
    current = email_writer(current)

    di = current.get("detected_intents")
    if not isinstance(di, list):
        di = []

    sent_at = datetime.now(timezone.utc).isoformat()
    save_reply(
        {
            "email_id": current["email_id"],
            "thread_id": current.get("thread_id", ""),
            "from_addr": RECRUITER_EMAIL or "recruiter@example.com",
            "to_addr": current.get("from_addr", ""),
            "subject": current.get("reply_subject", ""),
            "body": current.get("reply_body", ""),
            "sent_at": sent_at,
            "intent_label": current.get("intent_label", ""),
            "profile_type": current.get("profile_type", ""),
            "sender_name": RECRUITER_NAME or "",
            "detected_intents": di,
        }
    )
    update_email_status(current["email_id"], "processed")
    current["pipeline_stopped"] = "completed"
    return current


def _format_intents(detected_intents: list[dict[str, Any]] | None) -> str:
    if not detected_intents:
        return "(none)"
    parts = []
    for item in detected_intents:
        iid = item.get("intent_id")
        label = item.get("intent_label") or "Unknown"
        parts.append(f"{iid}: {label}")
    return "; ".join(parts)


def write_results_docx(results: list[dict[str, Any]], output_path: Path, *, source_doc: Path) -> None:
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as exc:
        raise SystemExit(
            "python-docx is required to write the report. Install with: pip install python-docx"
        ) from exc

    doc = Document()
    title = doc.add_heading("QA Email Replay — Pipeline Responses", level=0)
    title.runs[0].font.size = Pt(18) if title.runs else None

    meta = doc.add_paragraph()
    meta.add_run(f"Source document: {source_doc.name}\n").bold = True
    meta.add_run(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
    meta.add_run("Mode: dry-run (no emails sent, no DB status updates)\n")

    for row in results:
        case_id = row["id"]
        doc.add_heading(f"Email #{case_id}", level=1)

        doc.add_heading("Incoming email (candidate)", level=2)
        doc.add_paragraph(row.get("incoming_body") or "")

        doc.add_heading("Previous response (from source document)", level=2)
        doc.add_paragraph(row.get("baseline_response") or "(none recorded)")

        doc.add_heading("New pipeline response", level=2)
        if row.get("error"):
            doc.add_paragraph(f"ERROR: {row['error']}")
        elif row.get("pipeline_stopped") == "irrelevant":
            doc.add_paragraph(
                f"Marked irrelevant by relevance checker: {row.get('irrelevant_reason', '')}"
            )
        else:
            subj = doc.add_paragraph()
            subj.add_run("Subject: ").bold = True
            subj.add_run(row.get("reply_subject") or "")

            intents_p = doc.add_paragraph()
            intents_p.add_run("Detected intents: ").bold = True
            intents_p.add_run(row.get("detected_intents_text") or "")

            doc.add_paragraph(row.get("reply_body") or "(empty reply body)")

        doc.add_paragraph()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay QA docx emails through the reply pipeline.")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "Email 1_ (1).docx",
        help="Input .docx with EMAIL#N / RESPONSE sections",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .docx path (default: data/test_results/qa_replay_<timestamp>.docx)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional JSON dump of full pipeline state per email",
    )
    parser.add_argument(
        "--candidate-name",
        default="Alex Candidate",
        help="Candidate name passed to the email writer",
    )
    parser.add_argument(
        "--from-addr",
        default="candidate.qa@example.com",
        help="Synthetic from address for test emails",
    )
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated EMAIL# ids to run (e.g. 1,5,12). Default: all.",
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

    input_path = args.input.resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    cases = parse_qa_docx(input_path)
    if not cases:
        raise SystemExit(
            f"No email sections found in {input_path} "
            "(expected EMAIL#N or Email N: headers)"
        )

    if args.only.strip():
        wanted = {int(part.strip()) for part in args.only.split(",") if part.strip()}
        cases = [case for case in cases if case["id"] in wanted]
        if not cases:
            raise SystemExit(f"No matching EMAIL# ids in --only: {sorted(wanted)}")

    logger.info("Parsed %s test email(s) from %s", len(cases), input_path.name)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "data" / "test_results"
    output_path = (args.output or out_dir / f"qa_replay_{ts}.docx").resolve()
    json_path = args.json.resolve() if args.json else out_dir / f"qa_replay_{ts}.json"

    results: list[dict[str, Any]] = []
    json_payload: list[dict[str, Any]] = []

    for case in cases:
        logger.info("Processing EMAIL#%s ...", case["id"])
        row: dict[str, Any] = {
            "id": case["id"],
            "incoming_body": case["incoming_body"],
            "baseline_response": case["baseline_response"],
        }
        try:
            state = _build_initial_state(
                case,
                candidate_name=args.candidate_name,
                from_addr=args.from_addr,
            )
            result = run_reply_pipeline(state)
            row.update(
                {
                    "reply_subject": result.get("reply_subject", ""),
                    "reply_body": result.get("reply_body", ""),
                    "detected_intents": result.get("detected_intents"),
                    "detected_intents_text": _format_intents(result.get("detected_intents")),
                    "detected_concerns": result.get("detected_concerns"),
                    "email_summary": result.get("email_summary"),
                    "is_relevant": result.get("is_relevant"),
                    "irrelevant_reason": result.get("irrelevant_reason"),
                    "pipeline_stopped": result.get("pipeline_stopped"),
                    "reply_constraints": result.get("reply_constraints"),
                }
            )
            json_payload.append({"id": case["id"], "state": _json_safe(result)})
        except Exception as exc:
            logger.exception("EMAIL#%s failed", case["id"])
            row["error"] = str(exc)
            json_payload.append({"id": case["id"], "error": str(exc)})

        results.append(row)
        preview = (row.get("reply_body") or row.get("error") or "")[:120]
        logger.info("  -> %s", preview.replace("\n", " "))

    write_results_docx(results, output_path, source_doc=input_path)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "source": str(input_path),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "results": json_payload,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"\nParsed {len(cases)} email(s) from: {input_path}")
    print(f"Report document: {output_path}")
    print(f"JSON details:    {json_path}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


if __name__ == "__main__":
    main()
