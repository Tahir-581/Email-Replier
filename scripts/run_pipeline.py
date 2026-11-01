"""
scripts/run_pipeline.py

Unified entry point — runs the complete end-to-end pipeline:

  Step 1 (Layer 1 + 2): Gmail Puller → PostgreSQL DB      [collaborator's async pipeline]
  Step 2 (Layer 3+)   : DB → Agents → Reply + Log saved   [our sync pipeline]

Usage:
    python scripts/run_pipeline.py                  # run full pipeline (default limit=50)
    python scripts/run_pipeline.py --limit 10       # process max 10 emails from Gmail
    python scripts/run_pipeline.py --skip-pull      # skip Gmail pull, only process pending emails from DB
    python scripts/run_pipeline.py --batch-concurrency 1   # process pending emails one at a time
    python scripts/run_pipeline.py --monitor        # poll inbox + process every 60s until Ctrl+C
    python scripts/run_pipeline.py --monitor --skip-pull   # DB-only poll every 60s until Ctrl+C
    python scripts/run_pipeline.py --test           # test with single email (layer 1+2 only)
"""

import sys
import os
import asyncio
import logging
import time
from datetime import datetime


def _ensure_windows_selector_event_loop() -> None:
    # Psycopg3 async is incompatible with Windows' default ProactorEventLoop.
    if sys.platform != "win32":
        return
    windows_selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if windows_selector_policy is None:
        return
    if not isinstance(asyncio.get_event_loop_policy(), windows_selector_policy):
        asyncio.set_event_loop_policy(windows_selector_policy())

# ── Add project root + scripts dir to path ────────────────────────────────────
# Running `python scripts/run_pipeline.py` makes `scripts/` the first sys.path
# entry, which can cause `import scripts...` to resolve to a third-party PyPI
# package named `scripts` if installed. We avoid that by importing local modules
# directly after putting the project root + this folder on sys.path.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, _SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Collaborator's ingestion pipeline (Layer 1 + 2) ───────────────────────────
from pipeline_layers_1_2 import PipelineLayers1_2

# ── Our processing pipeline (Layer 3+) ───────────────────────────────────────
from src.pipeline.batch import process_email_batch


# =============================================================================
# Step 1 — Gmail Pull → DB  (collaborator's async pipeline)
# =============================================================================

async def run_ingestion(limit: int = 50, last_hours: float = 1.0) -> dict:
    """
    Run Layer 1 + Layer 2:
    Fetch emails from Gmail and write them to PostgreSQL.
    """
    logger.info("=" * 60)
    logger.info("STEP 1 — Gmail Pull → Database")
    logger.info("=" * 60)

    ingestion = PipelineLayers1_2()
    result = await ingestion.run_ingestion_pipeline(limit=limit, last_hours=last_hours)

    logger.info(f"Ingestion complete | fetched={result.get('total_fetched', 0)} | "
                f"stored={result.get('processed', 0)} | errors={result.get('errors', 0)}")
    return result


def _compact_email_preview(email: dict) -> dict:
    if not isinstance(email, dict):
        return {"type": str(type(email))}

    subject = (email.get("subject") or "").strip()
    from_addr = (email.get("from") or "").strip()
    to_addr = (email.get("to") or "").strip()
    body = email.get("body") or ""
    snippet = email.get("snippet") or ""

    return {
        "id": email.get("id"),
        "thread_id": email.get("thread_id"),
        "subject": (subject[:120] + "…") if len(subject) > 120 else subject,
        "from": (from_addr[:120] + "…") if len(from_addr) > 120 else from_addr,
        "to": (to_addr[:120] + "…") if len(to_addr) > 120 else to_addr,
        "date": email.get("date"),
        "snippet_preview": (snippet[:160] + "…") if len(snippet) > 160 else snippet,
        "body_len": len(body),
    }


# =============================================================================
# Step 2 — DB → Agents → Reply + Log  (our sync pipeline)
# =============================================================================

def run_processing(*, batch_concurrency: int | None = None) -> dict:
    """
    Run Layer 3+:
    Read pending emails from DB and process them through our agent pipeline.
    """
    logger.info("=" * 60)
    logger.info("STEP 2 — Database → Agent Pipeline")
    logger.info("=" * 60)

    result = process_email_batch(concurrency=batch_concurrency)
    if result["total"] == 0:
        logger.info("No pending emails found in database.")

    return {
        "processed": result["processed"],
        "errors": result["errors"],
        "deferred": result["deferred"],
    }


# =============================================================================
# Unified runner
# =============================================================================

CHECK_INTERVAL = 60  # seconds


async def run_full_pipeline(
    limit: int = 50,
    skip_pull: bool = False,
    continuous: bool = False,
    monitor: bool = False,
    last_hours: float = 1.0,
    batch_concurrency: int | None = None,
):
    """
    Run the complete end-to-end pipeline.

    Args:
        limit      : Max emails to pull from Gmail (ignored if skip_pull=True)
        skip_pull  : If True, skip Gmail pull and only process pending DB emails
        continuous : If True with skip_pull, same as --monitor --skip-pull (legacy)
        monitor    : If True, loop forever: rescan inbox (unless skip_pull) + process every CHECK_INTERVAL seconds
    """
    # Monitor mode: --monitor, or legacy --continuous --skip-pull
    monitor_loop = monitor or (continuous and skip_pull)
    if monitor_loop:
        effective_skip_pull = skip_pull if monitor else True

        logger.info("=" * 60)
        logger.info("EMAIL REPLIER — MONITOR MODE")
        logger.info("=" * 60)
        if effective_skip_pull:
            logger.info(f"Polling pending DB emails every {CHECK_INTERVAL} seconds (Gmail pull skipped).")
        else:
            logger.info(
                f"Polling Gmail inbox + agent pipeline every {CHECK_INTERVAL} seconds "
                f"(limit={limit}, last_hours={last_hours})."
            )
        logger.info("Press Ctrl+C to stop.\n")

        cycle = 0
        while True:
            cycle += 1
            try:
                logger.info(f"── Monitor cycle {cycle} ──")
                if not effective_skip_pull:
                    await run_ingestion(limit=limit, last_hours=last_hours)
                else:
                    logger.info("Skipping Gmail pull (--skip-pull).")

                run_processing(batch_concurrency=batch_concurrency)
                logger.info(f"Next scan in {CHECK_INTERVAL} seconds...\n")
                time.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                logger.info("\nShutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                time.sleep(CHECK_INTERVAL)
        return

    # One-time run
    start_time = datetime.now()

    logger.info("=" * 60)
    logger.info("EMAIL REPLIER — FULL PIPELINE START")
    logger.info("=" * 60)

    ingestion_result = {"total_fetched": 0, "processed": 0, "errors": 0}

    # ── Step 1: Gmail → DB ────────────────────────────────────────────────────
    if not skip_pull:
        ingestion_result = await run_ingestion(limit=limit, last_hours=last_hours)
    else:
        logger.info("Skipping Gmail pull (--skip-pull flag set).")

    # ── Step 2: DB → Agents ───────────────────────────────────────────────────
    processing_result = run_processing(batch_concurrency=batch_concurrency)

    # ── Summary ───────────────────────────────────────────────────────────────
    duration = (datetime.now() - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("FULL PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Gmail emails fetched : {ingestion_result.get('total_fetched', 0)}")
    logger.info(f"Emails stored to DB  : {ingestion_result.get('processed', 0)}")
    logger.info(f"Emails processed     : {processing_result.get('processed', 0)}")
    logger.info(f"Emails deferred      : {processing_result.get('deferred', 0)}")
    logger.info(f"Errors               : {ingestion_result.get('errors', 0) + processing_result.get('errors', 0)}")
    logger.info(f"Total duration       : {duration:.2f}s")
    logger.info("=" * 60)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Email Replier — Full Pipeline")
    parser.add_argument("--limit",     type=int, default=50,  help="Max emails to pull from Gmail (default: 50)")
    parser.add_argument("--skip-pull", action="store_true",   help="Skip Gmail pull, only process pending DB emails")
    parser.add_argument("--test",      action="store_true",   help="Test mode: pull 1 email only (Layer 1+2 only)")
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Keep running: rescan inbox and process every 60s until Ctrl+C (use --skip-pull for DB-only)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Legacy: same as --monitor --skip-pull (poll pending DB emails every 60s)",
    )
    parser.add_argument("--last-hours", type=float, default=1.0, help="Look back N hours for emails (default: 1)")
    parser.add_argument(
        "--batch-concurrency",
        type=int,
        default=None,
        metavar="N",
        help="Max emails processed in parallel (default: EMAIL_BATCH_CONCURRENCY env, usually 3; use 1 for sequential)",
    )

    args = parser.parse_args()
    _ensure_windows_selector_event_loop()

    if args.test:
        # Test mode: run only Layer 1+2 with 1 email
        async def test_mode():
            ingestion = PipelineLayers1_2()
            result = await ingestion.test_single_email()
            gmail_email = (result or {}).get("gmail_email") if isinstance(result, dict) else None
            if gmail_email:
                logger.info("Test result (compact): %s", _compact_email_preview(gmail_email))
            else:
                logger.info("Test result (raw): %s", result)

        asyncio.run(test_mode())

    else:
        asyncio.run(run_full_pipeline(
            limit=args.limit,
            skip_pull=args.skip_pull,
            continuous=args.continuous,
            monitor=args.monitor,
            last_hours=args.last_hours,
            batch_concurrency=args.batch_concurrency,
        ))
