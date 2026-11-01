"""
LangGraph pipeline for processing one pending email from the database.

Order:
    relevance -> history -> intent -> intent_persist -> policy -> writer -> sender -> log -> status

The Gmail puller and initial DB write happen before this graph runs.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.email_analyzer import email_analyzer
from src.agents.email_sender import email_sender
from src.agents.email_writer import email_writer
from src.agents.history_checker import history_checker
from src.agents.intent_classifier import intent_classifier
from src.agents.intent_persister import intent_persister
from src.agents.policy_engine import policy_engine
from src.agents.relevance_checker import relevance_checker
from src.agents.status_updater import status_updater
from src.db.session import update_email_status
from src.llm.errors import LLMError

logger = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    email_id: str
    message_id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    body: str
    date: Any
    received_at: str
    status: str
    is_relevant: bool
    irrelevant_reason: str | None
    history_records: list[dict[str, Any]]
    history_summary: str | None
    candidate_name: str
    email_summary: str
    detected_concerns: list[str]
    forms_already_shared: bool
    concern_count: int
    intent_id: int
    intent_label: str
    detected_intents: list[dict[str, Any]]
    detected_intents_json: str
    primary_intent_id: int
    primary_intent_label: str
    profile_type: str
    policy_prompt: str
    reply_constraints: dict[str, Any]
    reply_subject: str
    reply_body: str
    sent: bool
    sent_at: str | None
    log_written: bool
    error: str | None
    errors: list[str]
    failed_node: str | None


def _run_agent(agent_name: str, fn, state: GraphState) -> GraphState:
    try:
        state = fn(state)
        if state.get("error") and not state.get("failed_node"):
            state["failed_node"] = agent_name
        return state
    except LLMError:
        logger.exception("[%s] LLM failed for email_id=%s", agent_name, state.get("email_id"))
        raise
    except Exception as exc:
        logger.exception("[%s] failed for email_id=%s", agent_name, state.get("email_id"))
        errors = list(state.get("errors", []))
        errors.append(f"{agent_name}: {exc}")
        state["errors"] = errors
        state["error"] = str(exc)
        state["failed_node"] = agent_name
        state["status"] = "error"
        return state


def start_processing(state: GraphState) -> GraphState:
    state["status"] = "processing"
    update_email_status(state["email_id"], "processing")
    return state


def relevance_node(state: GraphState) -> GraphState:
    return _run_agent("relevance_checker", relevance_checker, state)


def history_node(state: GraphState) -> GraphState:
    return _run_agent("history_checker", history_checker, state)


def analyzer_node(state: GraphState) -> GraphState:
    return _run_agent("email_analyzer", email_analyzer, state)


def intent_node(state: GraphState) -> GraphState:
    return _run_agent("intent_classifier", intent_classifier, state)


def intent_persister_node(state: GraphState) -> GraphState:
    return _run_agent("intent_persister", intent_persister, state)


def policy_node(state: GraphState) -> GraphState:
    return _run_agent("policy_engine", policy_engine, state)


def writer_node(state: GraphState) -> GraphState:
    return _run_agent("email_writer", email_writer, state)


def sender_node(state: GraphState) -> GraphState:
    return _run_agent("email_sender", email_sender, state)


def finalize_irrelevant(state: GraphState) -> GraphState:
    state["status"] = "irrelevant"
    state["sent"] = False
    update_email_status(state["email_id"], "irrelevant")
    return state


def finalize_processed(state: GraphState) -> GraphState:
    if state.get("sent"):
        state["status"] = "processed"
        state["error"] = None
        update_email_status(state["email_id"], "processed")
    else:
        state["status"] = "error"
        update_email_status(state["email_id"], "error")
    return state


def finalize_error(state: GraphState) -> GraphState:
    state["status"] = "error"
    update_email_status(state["email_id"], "error")
    return state


def status_node(state: GraphState) -> GraphState:
    return _run_agent("status_updater", status_updater, state)


def route_after_relevance(state: GraphState) -> str:
    if state.get("status") == "error" or state.get("failed_node"):
        return "error"
    if not state.get("is_relevant", False):
        return "irrelevant"
    return "relevant"


def route_if_error(state: GraphState) -> str:
    if state.get("status") == "error" or state.get("failed_node"):
        return "error"
    return "ok"


def route_after_sender(state: GraphState) -> str:
    if state.get("status") == "error" or state.get("failed_node"):
        return "error"
    return "processed"


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("start_processing", start_processing)
    graph.add_node("relevance_checker", relevance_node)
    graph.add_node("history_checker", history_node)
    graph.add_node("email_analyzer", analyzer_node)
    graph.add_node("intent_classifier", intent_node)
    graph.add_node("intent_persister", intent_persister_node)
    graph.add_node("policy_engine", policy_node)
    graph.add_node("email_writer", writer_node)
    graph.add_node("email_sender", sender_node)
    graph.add_node("finalize_irrelevant", finalize_irrelevant)
    graph.add_node("finalize_processed", finalize_processed)
    graph.add_node("finalize_error", finalize_error)
    graph.add_node("status_updater", status_node)

    graph.set_entry_point("start_processing")
    graph.add_edge("start_processing", "relevance_checker")

    graph.add_conditional_edges(
        "relevance_checker",
        route_after_relevance,
        {
            "error": "finalize_error",
            "irrelevant": "finalize_irrelevant",
            "relevant": "history_checker",
        },
    )

    graph.add_conditional_edges("history_checker", route_if_error, {"error": "finalize_error", "ok": "email_analyzer"})
    graph.add_conditional_edges("email_analyzer", route_if_error, {"error": "finalize_error", "ok": "intent_classifier"})
    graph.add_conditional_edges("intent_classifier", route_if_error, {"error": "finalize_error", "ok": "intent_persister"})
    graph.add_conditional_edges("intent_persister", route_if_error, {"error": "finalize_error", "ok": "policy_engine"})
    graph.add_conditional_edges("policy_engine", route_if_error, {"error": "finalize_error", "ok": "email_writer"})
    graph.add_conditional_edges("email_writer", route_if_error, {"error": "finalize_error", "ok": "email_sender"})

    graph.add_conditional_edges(
        "email_sender",
        route_after_sender,
        {"error": "finalize_error", "processed": "finalize_processed"},
    )

    graph.add_edge("finalize_irrelevant", "status_updater")
    graph.add_edge("finalize_processed", "status_updater")
    graph.add_edge("finalize_error", "status_updater")
    graph.add_edge("status_updater", END)

    return graph.compile()


pipeline = build_graph()
