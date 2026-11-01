#!/usr/bin/env python3
"""
Layer 1 + Layer 2 Pipeline: Gmail Puller → DB Writer

Fetches emails from Gmail with thread history and stores them in database.
Enhanced with new gmail_puller features and VerificationState support.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Any

import structlog
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

try:
    # When executed/imported as `scripts.pipeline_layers_1_2`
    from .gmail_puller import get_gmail_puller  # type: ignore
except ImportError:
    # When executed/imported as a plain script/module (e.g. via sys.path hacks)
    from gmail_puller import get_gmail_puller
from src.agents.db_writer import email_db_writer
from src.pipeline.state import create_state_from_gmail_email, get_processing_summary

logger = structlog.get_logger(__name__)


class PipelineLayers1_2:
    """Layer 1 + Layer 2: Enhanced email ingestion and storage."""
    
    def __init__(self):
        self.processed_count = 0
        self.error_count = 0
        self.last_fetch_time = 0
        self.polling_interval = 30  # 30 seconds
    
    async def run_ingestion_pipeline(self, limit: int = 10, last_hours: float = 1.0) -> Dict[str, Any]:
        """
        Run complete Layer 1 + Layer 2 pipeline.
        
        Args:
            limit: Maximum number of emails to process
            last_hours: Look back window (in hours) for "new" emails
            
        Returns:
            Summary of processing results
        """
        
        logger.info(f"Starting Layer 1 + Layer 2 pipeline (limit: {limit}, last_hours: {last_hours})")
        start_time = datetime.now()
        
        try:
            # Layer 1: Enhanced Ingestion - Fetch emails from Gmail
            logger.info("[Layer 1] Fetching emails from Gmail...")
            puller = get_gmail_puller()
            
            # Use new fetch_new_emails for polling and duplicate prevention
            gmail_emails = await puller.fetch_new_emails(limit=limit, last_hours=last_hours)
            
            if not gmail_emails:
                logger.info("No new emails found in Gmail")
                return {
                    'processed': 0,
                    'errors': 0,
                    'duration_seconds': 0,
                    'message': 'No new emails found'
                }
            
            logger.info(f"[Layer 1] Fetched {len(gmail_emails)} new emails from Gmail")
            
            # Log thread history info
            total_history_messages = sum(len(email.get('history', [])) for email in gmail_emails)
            logger.info(f"[Thread history] {total_history_messages} total messages across {len(gmail_emails)} emails")
            
            # Layer 2: Storage - Write emails to database
            logger.info("[Layer 2] Storing emails in database...")
            
            processed_emails = []
            failed_emails = []
            
            for i, gmail_email in enumerate(gmail_emails, 1):
                logger.info(f"Processing email {i}/{len(gmail_emails)}: {gmail_email['subject'][:50]}...")
                
                try:
                    # Convert Gmail email to VerificationState
                    email_state = create_state_from_gmail_email(gmail_email)
                    
                    # Layer 2: Store in database
                    stored_state = await email_db_writer(email_state)
                    
                    if 'errors' in stored_state and stored_state['errors']:
                        failed_emails.append({
                            'email_id': gmail_email['id'],
                            'subject': gmail_email['subject'],
                            'error': stored_state['errors']
                        })
                        self.error_count += 1
                        logger.error(f"[ERROR] Failed to store email {gmail_email['id']}: {stored_state['errors']}")
                    else:
                        processed_emails.append({
                            'email_id': gmail_email['id'],
                            'subject': gmail_email['subject'],
                            'db_id': stored_state.get('email_db_id'),
                            'thread_id': gmail_email.get('thread_id')
                        })
                        self.processed_count += 1
                        logger.info(f"[OK] Stored email {gmail_email['id']} in database")
                    
                except Exception as e:
                    logger.error(f"[ERROR] Error processing email {i}: {e}")
                    failed_emails.append({
                            'email_id': gmail_email['id'],
                            'subject': gmail_email['subject'],
                            'error': str(e)
                        })
                    self.error_count += 1
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Prepare summary
            summary = {
                'processed': self.processed_count,
                'errors': self.error_count,
                'total_fetched': len(gmail_emails),
                'duration_seconds': duration,
                'processed_emails': processed_emails,
                'failed_emails': failed_emails,
                'success_rate': (self.processed_count / len(gmail_emails)) * 100 if gmail_emails else 0
            }
            
            logger.info("Pipeline completed!")
            logger.info(f"   Processed: {self.processed_count}")
            logger.info(f"   Errors: {self.error_count}")
            logger.info(f"   Duration: {duration:.2f}s")
            logger.info(f"   Success rate: {summary['success_rate']:.1f}%")
            
            return summary
            
        except Exception as e:
            logger.error(f"[ERROR] Pipeline failed: {e}")
            return {
                'processed': 0,
                'errors': 1,
                'duration_seconds': (datetime.now() - start_time).total_seconds(),
                'error': str(e)
            }
    
    async def run_continuous_ingestion(self, limit: int = 10, duration_minutes: int = None) -> Dict[str, Any]:
        """
        Run continuous ingestion with polling for specified duration or forever.
        
        Args:
            limit: Maximum emails per polling cycle
            duration_minutes: How long to run continuous polling (None = forever)
            
        Returns:
            Summary of continuous processing results
        """
        if duration_minutes:
            logger.info(f"[Polling] Starting continuous ingestion for {duration_minutes} minutes...")
            end_time = datetime.now().timestamp() + (duration_minutes * 60)
            has_time_limit = True
        else:
            logger.info("[Polling] Starting continuous ingestion forever (Ctrl+C to stop)...")
            has_time_limit = False
        
        start_time = datetime.now()
        cycle_count = 0
        total_processed = 0
        total_errors = 0
        
        while True:
            cycle_count += 1
            logger.info(f"[Polling] Cycle {cycle_count}...")
            
            try:
                # Run single ingestion cycle
                result = await self.run_ingestion_pipeline(limit=limit)
                
                total_processed += result.get('processed', 0)
                total_errors += result.get('errors', 0)
                
                if result.get('processed', 0) > 0:
                    logger.info(f"[OK] Cycle {cycle_count}: {result['processed']} emails processed")
                else:
                    logger.info(f"[Info] Cycle {cycle_count}: No new emails")
                
                # Check if we should stop (only if duration is set)
                if has_time_limit and datetime.now().timestamp() >= end_time:
                    logger.info("[Polling] Time limit reached - stopping continuous ingestion")
                    break
                
                # Wait for next polling cycle
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"[ERROR] Polling cycle {cycle_count} failed: {e}")
                total_errors += 1
                
                # Check if we should stop (only if duration is set)
                if has_time_limit and datetime.now().timestamp() >= end_time:
                    logger.info("[Polling] Time limit reached - stopping continuous ingestion")
                    break
                    
                await asyncio.sleep(self.polling_interval)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return {
            'cycles_completed': cycle_count,
            'total_processed': total_processed,
            'total_errors': total_errors,
            'duration_seconds': duration,
            'emails_per_minute': (total_processed / duration) * 60 if duration > 0 else 0
        }
    
    async def test_single_email(self) -> Dict[str, Any]:
        """Test pipeline with single email."""
        logger.info("[Test] Testing pipeline with single email...")
        
        # Fetch single email
        puller = get_gmail_puller()
        emails = await puller.fetch_emails(limit=1)
        
        if not emails:
            return {'error': 'No emails available for testing'}
        
        email = emails[0]
        logger.info(f"Test email: {email['subject']}")
        
        # Convert to state
        email_state = create_state_from_gmail_email(email)
        logger.info(f"[OK] State created: {email_state['email_id']}")
        
        # Store in database
        stored_state = await email_db_writer(email_state)
        logger.info(f"[OK] Stored in database: {stored_state.get('email_db_id')}")
        
        return {
            'gmail_email': email,
            'email_state': email_state,
            'stored_state': stored_state,
            'summary': get_processing_summary(stored_state)
        }


async def main():
    """Main function to run pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Layer 1 + Layer 2 Pipeline')
    parser.add_argument('--limit', type=int, default=50, help='Number of emails to process')
    parser.add_argument('--test', action='store_true', help='Test with single email')
    parser.add_argument('--continuous', nargs='?', const=-1, type=int, help='Run continuous ingestion for X minutes (or forever if no value)')
    parser.add_argument('--polling', type=int, default=30, help='Polling interval in seconds')
    parser.add_argument('--last-hours', type=float, default=1.0, help='Look back N hours for new emails (default: 1)')
    
    args = parser.parse_args()
    
    # Debug: Print parsed arguments
    print(f"[Args] test={args.test}, continuous={args.continuous}, limit={args.limit}, polling={args.polling}, last_hours={args.last_hours}")
    
    pipeline = PipelineLayers1_2()
    if args.polling:
        pipeline.polling_interval = args.polling
    
    print(f"[Args check] test={args.test}, continuous={args.continuous}, is_not_none={args.continuous is not None}")
    
    if args.test:
        # Test mode
        print("[Test] Running TEST mode")
        result = await pipeline.test_single_email()
        print("\n[Test] RESULT:")
        print(f"Email ID: {result['email_state']['email_id']}")
        print(f"Subject: {result['email_state']['subject']}")
        print(f"Thread ID: {result['gmail_email'].get('thread_id')}")
        print(f"History: {len(result['gmail_email'].get('history', []))} messages")
        print(f"DB ID: {result['stored_state'].get('email_db_id')}")
        print(f"Status: {result['stored_state'].get('status')}")
    elif args.continuous is not None:
        print("[Polling] Running CONTINUOUS mode")
        # Continuous mode
        # Handle continuous argument format
        duration = None
        if args.continuous == -1:
            duration = None  # Forever mode
        elif args.continuous is not None:
            duration = args.continuous
        result = await pipeline.run_continuous_ingestion(limit=args.limit, duration_minutes=duration)
        print(f"\n[Polling] CONTINUOUS INGESTION SUMMARY:")
        print(f"   Cycles completed: {result['cycles_completed']}")
        print(f"   📧 Total processed: {result['total_processed']}")
        print(f"   Total errors: {result['total_errors']}")
        print(f"   Duration: {result['duration_seconds']:.2f}s")
        print(f"   Emails/minute: {result['emails_per_minute']:.1f}")
    else:
        # Normal mode
        result = await pipeline.run_ingestion_pipeline(limit=args.limit, last_hours=args.last_hours)
        print(f"\nPIPELINE SUMMARY:")
        print(f"   Total fetched: {result['total_fetched']}")
        print(f"   Successfully processed: {result['processed']}")
        print(f"   Errors: {result['errors']}")
        print(f"   Success rate: {result['success_rate']:.1f}%")
        print(f"   Duration: {result['duration_seconds']:.2f}s")
        
        # Show thread history info
        if result.get('processed_emails'):
            total_history = sum(email.get('history_count', 0) for email in result['processed_emails'])
            print(f"   Thread history: {total_history} total messages")
        
        if result.get('failed_emails'):
            print(f"\n[ERROR] Failed emails:")
            for failed in result['failed_emails']:
                print(f"   - {failed['subject'][:50]}... | {failed['error']}")


if __name__ == "__main__":
    if sys.platform == "win32":
        windows_selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if windows_selector_policy is not None and not isinstance(asyncio.get_event_loop_policy(), windows_selector_policy):
            asyncio.set_event_loop_policy(windows_selector_policy())
    asyncio.run(main())
