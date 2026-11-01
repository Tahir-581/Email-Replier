#!/usr/bin/env python3
"""
Test Pipeline: Gmail Puller → EmailState → JSON Export
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import structlog

# Ensure project root is on sys.path when running as a script:
#   python scripts/test_gmail_to_json.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Also ensure this folder is on path so we can import `gmail_puller.py`
# without depending on the name `scripts` being an importable package.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

def _try_force_utf8_stdio() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


_try_force_utf8_stdio()

from gmail_puller import get_gmail_puller

logger = structlog.get_logger(__name__)


class GmailToJSONExporter:

    def __init__(self, output_dir: str = "email_exports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.exported_count = 0
        self.error_count = 0

    # =========================
    # EMAIL CONVERSION
    # =========================
    def gmail_to_emailstate(self, gmail_email: Dict[str, Any]) -> Dict[str, Any]:

        try:
            from email.utils import parsedate_to_datetime

            date_obj = parsedate_to_datetime(gmail_email['date'])
            if date_obj.tzinfo is None:
                date_obj = date_obj.replace(tzinfo=datetime.now().astimezone().tzinfo)

            def clean_email_addr(email_str):
                if '<' in email_str and '>' in email_str:
                    return email_str.split('<')[1].split('>')[0].strip()
                return email_str.strip()

            email_state = {
                'email_id': gmail_email['id'],
                'message_id': gmail_email.get('message_id', gmail_email['id']),
                'thread_id': gmail_email.get('thread_id', gmail_email['id']),

                'subject': gmail_email['subject'],
                'from_addr': clean_email_addr(gmail_email['from']),
                'to_addr': clean_email_addr(gmail_email['to']),

                'date': date_obj.isoformat(),
                'body': gmail_email['body'],

                'status': 'pending',
                'snippet': gmail_email.get('snippet', ''),
                'gmail_id': gmail_email['id'],

                # 🔥 ONLY ADDITION (safe)
                "history": []
            }

            return email_state

        except Exception as e:
            logger.error(f"Error converting Gmail email: {e}")
            return None

    # =========================
    # SAVE EMAIL
    # =========================
    def save_email_to_json(self, email_state: Dict[str, Any], index: int) -> bool:

        try:
            safe_subject = "".join(
                c for c in email_state['subject'][:50]
                if c.isalnum() or c in (' ', '-', '_')
            ).rstrip()

            filename = f"{index:03d}_{email_state['email_id']}_{safe_subject}.json"
            filepath = self.output_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(email_state, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Saved email {index}")
            return True

        except Exception as e:
            logger.error(f"Save error: {e}")
            return False

    # =========================
    # BUILD HISTORY (ONLY LOGIC ADD)
    # =========================
    def build_history(self, gmail_emails: List[Dict[str, Any]], current_email: Dict[str, Any]):

        try:
            from email.utils import parsedate_to_datetime
            thread_id = current_email.get("thread_id")

            # filter same thread
            thread_msgs = [
                m for m in gmail_emails
                if m.get("thread_id") == thread_id
            ]

            # sort by date
            thread_msgs.sort(
                key=lambda x: parsedate_to_datetime(x['date'])
            )

            history = []

            # find current index
            for i, msg in enumerate(thread_msgs):
                if msg["id"] == current_email["id"]:

                    # take previous 2 only
                    prev_msgs = thread_msgs[max(0, i-2):i]

                    for p in prev_msgs:
                        history.append({
                            "from_addr": p.get("from", ""),
                            "to_addr": p.get("to", ""),
                            "body": p.get("body", ""),
                            "date": p.get("date", "")
                        })
                    break

            return history

        except Exception as e:
            logger.error(f"History build error: {e}")
            return []

    # =========================
    # PIPELINE
    # =========================
    async def run_export_pipeline(self, limit: int = 100):

        logger.info(f"Starting pipeline (limit: {limit})")

        try:
            puller = get_gmail_puller()
            gmail_emails = await puller.fetch_emails(limit=limit)

            if not gmail_emails:
                return {"success": False, "error": "No emails fetched"}

            email_states = []

            # =========================
            # MAIN LOOP (SAFE CHANGE ONLY)
            # =========================
            for i, email in enumerate(gmail_emails, 1):

                try:
                    email_state = self.gmail_to_emailstate(email)

                    if email_state:

                        # 🔥 ADD HISTORY HERE (ONLY NEW PART)
                        email_state["history"] = self.build_history(
                            gmail_emails,
                            email
                        )

                        email_states.append(email_state)

                    else:
                        self.error_count += 1

                except Exception as e:
                    self.error_count += 1
                    logger.error(f"Error: {e}")

            # SAVE
            for i, state in enumerate(email_states, 1):
                if self.save_email_to_json(state, i):
                    self.exported_count += 1
                else:
                    self.error_count += 1

            return {
                "success": True,
                "total_fetched": len(gmail_emails),
                "total_exported": self.exported_count,
                "total_errors": self.error_count,
                "output_dir": str(self.output_dir)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# =========================
# RUN
# =========================
async def main():
    exporter = GmailToJSONExporter()
    result = await exporter.run_export_pipeline(limit=50)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())