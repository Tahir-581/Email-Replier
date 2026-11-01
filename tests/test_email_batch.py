import unittest
from unittest.mock import patch

from src.llm.errors import LLMError
from src.pipeline import batch


class EmailBatchTests(unittest.TestCase):
    def test_empty_batch(self):
        with patch.object(batch, "get_pending_emails", return_value=[]):
            result = batch.process_email_batch()
        self.assertEqual(result, {"total": 0, "processed": 0, "errors": 0, "deferred": 0})

    def test_sequential_success(self):
        emails = [
            {"email_id": "a", "from_addr": "a@example.com"},
            {"email_id": "b", "from_addr": "b@example.com"},
        ]
        with patch.object(batch, "pipeline") as mock_pipeline:
            mock_pipeline.invoke.side_effect = [
                {"status": "processed", "intent_id": 1},
                {"status": "processed", "intent_id": 2},
            ]
            result = batch.process_email_batch(emails, concurrency=1)

        self.assertEqual(result["processed"], 2)
        self.assertEqual(mock_pipeline.invoke.call_count, 2)

    def test_parallel_runs_all_emails(self):
        emails = [{"email_id": f"id-{i}", "from_addr": f"u{i}@example.com"} for i in range(4)]
        with patch.object(batch, "pipeline") as mock_pipeline:
            mock_pipeline.invoke.return_value = {"status": "processed"}
            result = batch.process_email_batch(emails, concurrency=4)

        self.assertEqual(result["total"], 4)
        self.assertEqual(result["processed"], 4)
        self.assertEqual(mock_pipeline.invoke.call_count, 4)

    def test_llm_error_defers_single_email_without_blocking_others(self):
        emails = [
            {"email_id": "ok", "from_addr": "ok@example.com"},
            {"email_id": "fail", "from_addr": "fail@example.com"},
        ]

        def invoke(email):
            if email["email_id"] == "fail":
                raise LLMError("down")
            return {"status": "processed"}

        with patch.object(batch, "pipeline") as mock_pipeline:
            mock_pipeline.invoke.side_effect = invoke
            with patch.object(batch, "update_email_status") as mock_status:
                result = batch.process_email_batch(emails, concurrency=2)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["deferred"], 1)
        mock_status.assert_called_once_with("fail", "pending")

    def test_pipeline_error_status_counts_as_error(self):
        emails = [{"email_id": "x", "from_addr": "x@example.com"}]
        with patch.object(batch, "pipeline") as mock_pipeline:
            mock_pipeline.invoke.return_value = {"status": "error"}
            result = batch.process_email_batch(emails, concurrency=1)

        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["processed"], 0)


if __name__ == "__main__":
    unittest.main()
