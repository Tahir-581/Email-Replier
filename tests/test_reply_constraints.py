import unittest

from scripts.reply_regression_cases import REGRESSION_CASES
from src.llm.prompts import email_writer as email_writer_prompt
from src.llm.prompts import intent_classifier as intent_classifier_prompt
from src.llm.prompts import policy_engine as policy_prompt
from src.utils.config import INTENT_BUCKETS
from src.utils.reply_constraints import (
    LINKEDIN_TOUCHPOINT_SENTENCE,
    derive_reply_constraints,
    ensure_linkedin_url_on_touchpoint,
    format_constraints,
    mentions_linkedin_touchpoint,
    recruiter_linkedin_url,
)


class ReplyConstraintRegressionTests(unittest.TestCase):
    def _state_for_case(self, case):
        return {
            "body": case["body"],
            "email_summary": case["body"],
            "detected_concerns": [case["body"]],
            "detected_intents": [
                {"intent_id": intent_id, "intent_label": INTENT_BUCKETS[intent_id]}
                for intent_id in case["intent_ids"]
            ],
            "forms_already_shared": case.get("forms_already_shared", False),
            "profile_type": case.get("profile_type", "unknown"),
        }

    def test_regression_dataset_has_43_cases(self):
        self.assertEqual(len(REGRESSION_CASES), 43)

    def test_constraints_match_regression_expectations(self):
        for case in REGRESSION_CASES:
            with self.subTest(case=case["name"]):
                constraints = derive_reply_constraints(self._state_for_case(case))
                self.assertEqual(
                    constraints["company_intro_allowed"],
                    case["expect_company_intro_allowed"],
                )
                if case.get("expect_no_forms"):
                    self.assertEqual(
                        constraints["forms_to_share"], [], f"Unexpected forms for {case['name']}"
                    )
                if "expect_forms" in case:
                    self.assertEqual(constraints["forms_to_share"], case["expect_forms"])

    def test_forms_resharing_rule_is_exposed(self):
        case = next(c for c in REGRESSION_CASES if c["name"] == "forms_already_shared_frontend")
        constraints = derive_reply_constraints(self._state_for_case(case))
        self.assertIn("avoid resharing", constraints["forms_reason"].lower())

    def test_prompt_systems_include_new_guardrails(self):
        self.assertIn("Never use the phrase \"I respect your decision\"", policy_prompt.SYSTEM)
        self.assertIn("Candidate requests interview reschedule", intent_classifier_prompt.SYSTEM)
        self.assertIn("Never say \"I respect your decision\"", email_writer_prompt.SYSTEM)
        self.assertIn("Candidate requests internship / completion certificate", intent_classifier_prompt.SYSTEM)
        self.assertIn("Candidate complains about management / poor experience", intent_classifier_prompt.SYSTEM)

    def test_constraints_text_exposes_priority_and_guardrails(self):
        constraints = derive_reply_constraints(self._state_for_case(REGRESSION_CASES[0]))
        text = format_constraints(constraints)
        self.assertIn("Answer this first", text)
        self.assertIn("Guardrail", text)
        self.assertIn("Company intro allowed: no", text)

    def test_intent_taxonomy_expanded(self):
        self.assertGreaterEqual(len(INTENT_BUCKETS), 28)
        self.assertEqual(INTENT_BUCKETS[16], "Candidate complains about management / poor experience")
        self.assertEqual(INTENT_BUCKETS[23], "Candidate requests internship / completion certificate")
        self.assertEqual(INTENT_BUCKETS[28], "Candidate shares portfolio / CV for non-AI role review")

    def test_linkedin_touchpoint_detection(self):
        self.assertTrue(mentions_linkedin_touchpoint(LINKEDIN_TOUCHPOINT_SENTENCE))
        self.assertTrue(
            mentions_linkedin_touchpoint(
                "I invite you to connect with me on LinkedIn for future touchpoints."
            )
        )
        self.assertFalse(mentions_linkedin_touchpoint("Please share your CV."))

    def test_ensure_linkedin_url_appended_for_touchpoint(self):
        body = f"Hi,\n\n{LINKEDIN_TOUCHPOINT_SENTENCE}"
        result = ensure_linkedin_url_on_touchpoint(body)
        self.assertIn("linkedin.com/in/your-recruiter-profile", result.lower())

    def test_ensure_linkedin_url_not_duplicated(self):
        url = f"{recruiter_linkedin_url()}/"
        body = f"Hi,\n\n{LINKEDIN_TOUCHPOINT_SENTENCE}\n{url}"
        self.assertEqual(ensure_linkedin_url_on_touchpoint(body), body)

    def test_constraints_include_linkedin_url_when_allowed(self):
        case = next(c for c in REGRESSION_CASES if 1 in c["intent_ids"])
        constraints = derive_reply_constraints(self._state_for_case(case))
        text = format_constraints(constraints)
        self.assertIn("LinkedIn touchpoint line", text)
        self.assertIn("linkedin.com/in/your-recruiter-profile", text.lower())


if __name__ == "__main__":
    unittest.main()
