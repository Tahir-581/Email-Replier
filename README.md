# Email-Replier — LangGraph recruiting email agent + dashboard

An agent that reads candidate emails from Gmail, works out what each candidate is asking, and drafts a policy-compliant reply that a person reviews before it is sent. It ships with a FastAPI backend, PostgreSQL storage and a Next.js dashboard. The dashboard also has a small email-campaign module.

All company details in the prompts are placeholders ("Acme Corp"). Edit the facts in `src/llm/prompts/policy_engine.py` and the values in `.env` for your own organization.

## How it works

A LangGraph `StateGraph` (`src/pipeline/graph.py`) runs each email through these nodes:

```
relevance_checker → history_checker → email_analyzer → intent_classifier
   → intent_persister → policy_engine → email_writer → email_sender → status_updater
```

- **Intent classification:** each email is mapped to one or more of **28 intent buckets** (`INTENT_BUCKETS` in `src/utils/config.py`), such as salary questions, relocation, remote work, internships or follow-ups. The full reference is in `data/email_reply_intents.txt`.
- **Policy engine and writer:** the LLM gets a per-intent rulebook, and `src/utils/reply_constraints.py` enforces which forms, links and company info may appear in a reply.
- **Human in the loop:** with `SEND_EMAILS_DIRECTLY=false` (the default), replies are stored as drafts. They are reviewed, edited and sent from the dashboard's HR inbox.
- **Logging:** emails, replies and pipeline logs are stored in PostgreSQL (SQLAlchemy models plus Alembic migrations in `src/db/`).
- **LLM:** any OpenAI-compatible chat completions endpoint, set with `LLM_BASE_URL` (for example a self-hosted vLLM server). LLM JSON output is repaired with `json-repair` and validated into typed pipeline state.

## Stack

| Layer | Tech |
|---|---|
| Agent | LangGraph, LangChain core, httpx, tenacity |
| API | FastAPI, JWT auth, Pydantic schemas / pydantic-settings |
| DB | PostgreSQL, SQLAlchemy, Alembic |
| Mail | Gmail API (OAuth) for ingest/replies; Resend for campaigns |
| UI | Next.js, Tailwind (`apps/web`) |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in database, LLM, Gmail, JWT values
python scripts/setup_gmail_oauth.py
(cd src/db && alembic upgrade head)
python scripts/seed_dashboard_demo.py   # optional synthetic demo data
uvicorn src.api.main:app --reload --port 8000
```

Dashboard:

```bash
cd apps/web && npm install && npm run dev   # http://localhost:3000
```

Run the pipeline from the CLI:

```bash
python scripts/run_pipeline.py              # pull from Gmail and process
python scripts/run_pipeline.py --skip-pull  # process already-stored emails
```

## Tests

```bash
pytest tests
python scripts/test_multi_intent.py   # synthetic multi-intent example
```

The regression cases in `scripts/reply_regression_cases.py` are short anonymised example emails.

## Layout

```
apps/web/        Next.js dashboard
src/pipeline/    LangGraph graph, batch runner, state
src/agents/      graph nodes (relevance, history, intent, policy, writer, sender)
src/llm/         LLM client + prompts
src/api/         FastAPI routers (auth, hr, contacts, templates, campaigns, settings)
src/db/          models + Alembic migrations
scripts/         CLI utilities
```

## License

MIT
