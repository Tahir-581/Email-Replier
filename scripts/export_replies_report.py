"""
Export reply-pair JSON (from generate_replies_json.py) to formatted DOCX and PDF reports.

Each email section shows the received message first, then the generated reply,
with From/Subject headers and detected intents.

Usage (from repo root):
    python scripts/export_replies_report.py
    python scripts/export_replies_report.py --input data/test_results/email1_v2_replies.json
    python scripts/export_replies_report.py --docx-only
    python scripts/export_replies_report.py --pdf-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_replies_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Input file not found: {path}")

    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise SystemExit(f"No results found in {path}")

    return payload


def _body_paragraphs(text: str | None) -> list[str]:
    if not text:
        return ["(empty)"]

    lines = text.split("\n")
    paragraphs: list[str] = []
    buffer: list[str] = []

    for line in lines:
        if line.strip():
            buffer.append(line.rstrip())
        elif buffer:
            paragraphs.append("\n".join(buffer))
            buffer = []

    if buffer:
        paragraphs.append("\n".join(buffer))

    return paragraphs or ["(empty)"]


def _format_intents(detected_intents: list[dict[str, Any]] | None) -> str:
    if not detected_intents:
        return "(none)"
    parts = []
    for item in detected_intents:
        iid = item.get("intent_id")
        label = item.get("intent_label") or "Unknown"
        parts.append(f"{iid}: {label}")
    return "; ".join(parts)


def _resolve_reply_section(result: dict[str, Any]) -> tuple[str, str, str | None]:
    """Return (subject, body, optional_note) for the generated reply section."""
    status = result.get("status") or "completed"
    generated = result.get("generated_email") or {}

    if status == "error":
        return (
            "",
            "",
            f"ERROR: {result.get('error') or 'Unknown error'}",
        )

    if status == "irrelevant" or generated is None:
        reason = result.get("irrelevant_reason") or "Marked irrelevant by pipeline"
        return ("", "", f"Marked irrelevant: {reason}")

    return (
        generated.get("subject") or "",
        generated.get("body") or "(empty reply body)",
        None,
    )


def _source_name(payload: dict[str, Any]) -> str:
    source = payload.get("source") or ""
    if source:
        return Path(source).name
    return "(unknown)"


def _sorted_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(payload["results"], key=lambda row: int(row.get("id") or 0))


def write_docx_report(payload: dict[str, Any], output_path: Path) -> None:
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as exc:
        raise SystemExit(
            "python-docx is required to write the report. Install with: pip install python-docx"
        ) from exc

    doc = Document()
    title = doc.add_heading("Email Reply Report", level=0)
    if title.runs:
        title.runs[0].font.size = Pt(18)

    meta = doc.add_paragraph()
    meta.add_run(f"Source: {_source_name(payload)}\n").bold = True
    meta.add_run(f"Generated: {payload.get('generated_at', '(unknown)')}\n")
    meta.add_run(f"Total emails: {payload.get('count', len(payload['results']))}\n")

    for result in _sorted_results(payload):
        case_id = result.get("id")
        input_email = result.get("input_email") or {}

        doc.add_heading(f"Email #{case_id}", level=1)

        doc.add_heading("Received email", level=2)
        from_p = doc.add_paragraph()
        from_p.add_run("From: ").bold = True
        from_addr = input_email.get("from_addr") or ""
        candidate = input_email.get("candidate_name") or ""
        from_p.add_run(f"{candidate} <{from_addr}>" if candidate else from_addr)

        subj_p = doc.add_paragraph()
        subj_p.add_run("Subject: ").bold = True
        subj_p.add_run(input_email.get("subject") or "")

        for paragraph in _body_paragraphs(input_email.get("body")):
            doc.add_paragraph(paragraph)

        doc.add_heading("Generated reply", level=2)
        reply_subject, reply_body, reply_note = _resolve_reply_section(result)

        if reply_note:
            doc.add_paragraph(reply_note)
        else:
            reply_subj_p = doc.add_paragraph()
            reply_subj_p.add_run("Subject: ").bold = True
            reply_subj_p.add_run(reply_subject)

            for paragraph in _body_paragraphs(reply_body):
                doc.add_paragraph(paragraph)

        intents_p = doc.add_paragraph()
        intents_p.add_run("Detected intents: ").bold = True
        intents_p.add_run(_format_intents(result.get("detected_intents")))

        doc.add_paragraph()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def _resolve_pdf_fonts() -> tuple[Path, Path]:
    """Return (regular_ttf, bold_ttf) paths for PDF Unicode text."""
    candidates: list[tuple[Path, Path]] = [
        (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/Library/Fonts/Arial.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            return regular, bold

    raise SystemExit(
        "No suitable Unicode TTF fonts found for PDF export. "
        "Install DejaVu fonts or run on Windows/macOS with standard system fonts."
    )


def write_pdf_report(payload: dict[str, Any], output_path: Path) -> None:
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise SystemExit(
            "fpdf2 is required to write the PDF report. Install with: pip install fpdf2"
        ) from exc

    regular_font, bold_font = _resolve_pdf_fonts()

    class ReportPDF(FPDF):
        def header(self) -> None:
            return

        def footer(self) -> None:
            self.set_y(-15)
            self.set_font("Report", size=9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")

        def _write_block(self, text: str, *, size: int = 10, bold: bool = False, line_height: float = 6) -> None:
            self.set_x(self.l_margin)
            self.set_font("Report", style="B" if bold else "", size=size)
            self.multi_cell(self.epw, line_height, text)

        def section_heading(self, text: str, size: int = 14) -> None:
            self.ln(4)
            self.set_text_color(0, 0, 0)
            self._write_block(text, size=size, bold=True, line_height=8)
            self.ln(2)

        def sub_heading(self, text: str) -> None:
            self._write_block(text, size=12, bold=True, line_height=7)
            self.ln(1)

        def labeled_line(self, label: str, value: str) -> None:
            self._write_block(f"{label}: {value or ''}", size=10, bold=False)

        def body_text(self, text: str | None) -> None:
            for paragraph in _body_paragraphs(text):
                self._write_block(paragraph, size=10, bold=False)
                self.ln(2)

    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.add_font("Report", "", fname=str(regular_font))
    pdf.add_font("Report", "B", fname=str(bold_font))

    pdf.set_font("Report", style="B", size=16)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 10, "Email Reply Report")
    pdf.ln(4)

    pdf.set_font("Report", size=10)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, f"Source: {_source_name(payload)}")
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, f"Generated: {payload.get('generated_at', '(unknown)')}")
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 6, f"Total emails: {payload.get('count', len(payload['results']))}")
    pdf.ln(6)

    results = _sorted_results(payload)
    for index, result in enumerate(results):
        if index > 0:
            pdf.ln(8)

        case_id = result.get("id")
        input_email = result.get("input_email") or {}

        pdf.section_heading(f"Email #{case_id}")

        pdf.sub_heading("Received email")
        from_addr = input_email.get("from_addr") or ""
        candidate = input_email.get("candidate_name") or ""
        from_value = f"{candidate} <{from_addr}>" if candidate else from_addr
        pdf.labeled_line("From", from_value)
        pdf.labeled_line("Subject", input_email.get("subject") or "")
        pdf.body_text(input_email.get("body"))

        pdf.sub_heading("Generated reply")
        reply_subject, reply_body, reply_note = _resolve_reply_section(result)
        if reply_note:
            pdf.body_text(reply_note)
        else:
            pdf.labeled_line("Subject", reply_subject)
            pdf.body_text(reply_body)

        pdf.labeled_line("Detected intents", _format_intents(result.get("detected_intents")))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))


def main() -> None:
    default_input = PROJECT_ROOT / "data" / "test_results" / "email1_v2_replies.json"

    parser = argparse.ArgumentParser(
        description="Export reply-pair JSON to formatted DOCX and PDF reports.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help=f"Input JSON path (default: {default_input.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--output-docx",
        type=Path,
        default=None,
        help="Output DOCX path (default: same stem as input with .docx)",
    )
    parser.add_argument(
        "--output-pdf",
        type=Path,
        default=None,
        help="Output PDF path (default: same stem as input with .pdf)",
    )
    parser.add_argument(
        "--docx-only",
        action="store_true",
        help="Write only the DOCX report",
    )
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Write only the PDF report",
    )
    args = parser.parse_args()

    if args.docx_only and args.pdf_only:
        raise SystemExit("Use only one of --docx-only or --pdf-only.")

    input_path = args.input.resolve()
    payload = load_replies_json(input_path)

    stem = input_path.with_suffix("")
    output_docx = (args.output_docx or stem.with_suffix(".docx")).resolve()
    output_pdf = (args.output_pdf or stem.with_suffix(".pdf")).resolve()

    write_docx = not args.pdf_only
    write_pdf = not args.docx_only

    if write_docx:
        write_docx_report(payload, output_docx)
        print(f"DOCX written: {output_docx}")

    if write_pdf:
        write_pdf_report(payload, output_pdf)
        print(f"PDF written: {output_pdf}")


if __name__ == "__main__":
    main()
