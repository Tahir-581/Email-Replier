"""Tests for QA document paragraph parsing (EMAIL#N and Email N: formats)."""

from scripts.replay_qa_docx_emails import parse_qa_paragraphs


def test_parse_email_hash_headers():
    paragraphs = [
        "EMAIL#1",
        "First incoming line.",
        "RESPONSE:",
        "Baseline reply.",
        "EMAIL#2",
        "Second incoming.",
        "RESPONSE:",
        "Second reply.",
    ]
    cases = parse_qa_paragraphs(paragraphs)
    assert len(cases) == 2
    assert cases[0]["id"] == 1
    assert cases[0]["incoming_body"] == "First incoming line."
    assert cases[0]["baseline_response"] == "Baseline reply."
    assert cases[1]["incoming_body"] == "Second incoming."


def test_parse_email_number_colon_headers():
    paragraphs = [
        "Email 1:",
        "Hi i want to say one thing your management is very bad.",
        "Response:",
        "Hi Jane Doe,",
        "Thanks for getting back.",
        "Email 2:",
        "Hi i am a frontend developer.",
        "Response :",
        "Thanks for your message.",
    ]
    cases = parse_qa_paragraphs(paragraphs)
    assert len(cases) == 2
    assert cases[0]["id"] == 1
    assert "management is very bad" in cases[0]["incoming_body"]
    assert "Jane Doe" in cases[0]["baseline_response"]
    assert cases[1]["id"] == 2
    assert "frontend developer" in cases[1]["incoming_body"]
