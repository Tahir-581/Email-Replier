# Email Replier — setup instructions

This guide walks through copying and filling environment variables from `.env.example`, preparing PostgreSQL, Gmail OAuth, and the LLM endpoint so you can run the pipeline end to end.

---

## 1. Prerequisites

- **Python** 3.10 or newer (3.11+ recommended).
- **PostgreSQL** with a database user that can create extensions (for `pgcrypto`, used by UUID defaults in some schemas).
- **Google Cloud** project where you can enable the **Gmail API** and create **OAuth 2.0** credentials.
- Network access to your **OpenAI-compatible LLM** HTTP endpoint (the app posts JSON to a chat-completions-style URL).

---

## 2. Clone and create a virtual environment

From the repository root (`email-replier/`):

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Create `.env` from `.env.example`

1. Copy the example file to `.env` in the **repository root** (same folder as `requirements.txt`).
2. Open `.env` in an editor.

**Important:** `.env.example` currently lists **two different PostgreSQL configurations** (local vs remote). Keep **only one** consistent block:

- Either use **local** Postgres (`localhost`) **or** your remote host — not both. Duplicate `DATABASE_URL` / `DATABASE_BASE_URL` keys mean the **last** assignment wins, which is easy to get wrong.

The application loads settings from `.env` via `src/utils/config.py`. It normalizes database URLs to use **`postgresql+asyncpg`** for async SQLAlchemy.

**Security:** Never commit `.env` or real secrets. Treat `.env.example` as a template only.

---

## 4. Environment variables (from `.env.example`)

Fill each variable below. Names match `.env.example` unless noted.

### 4.1 Database — `DATABASE_URL`, `DATABASE_BASE_URL`, `EMAIL_DB`

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Full SQLAlchemy async URL to your **application database** (includes database name). Example: `postgresql+asyncpg://USER:PASSWORD@HOST:5432/email_replier` |
| `DATABASE_BASE_URL` | Same server and credentials, path **only** to the server root: `postgresql+asyncpg://USER:PASSWORD@HOST:5432/` (trailing slash before DB name is optional; the app strips/splits as needed). |
| `EMAIL_DB` | Database **name** only (default in example: `email_replier`). If `DATABASE_URL` is empty, the app can build it from `DATABASE_BASE_URL` + `EMAIL_DB`. |

**Steps:**

1. Create the database (example name: `email_replier`). You can use `helper-scripts/create_local_db.py` if your local Postgres matches its defaults (`postgres` / `postgres` on `localhost:5432`), or create the DB manually:

   ```sql
   CREATE DATABASE email_replier;
   ```

2. Enable **`pgcrypto`** (needed where schemas use `gen_random_uuid()`):

   ```sql
   \c email_replier
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```

   Alternatively, if your sync URL in `.env` is a plain `postgresql://...` (not `postgresql+asyncpg`), you can run `python helper-scripts/ensure_pgcrypto.py` after fixing that script’s expectation or run the SQL above with `psql`.


---

### 4.2 Gmail OAuth — `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `GMAIL_TOKEN_FILE`

These drive **Gmail API** access: reading mail and **creating drafts** (the sender creates a draft; it does not auto-send).

| Variable | Purpose |
|----------|---------|
| `GMAIL_CLIENT_ID` | OAuth 2.0 Client ID from Google Cloud Console |
| `GMAIL_CLIENT_SECRET` | Client secret for that client |
| `GMAIL_REDIRECT_URI` | Must match what you register in Google Cloud. The setup script defaults to **`http://localhost:8085/`** if unset or invalid — register this **exact** URI |
| `GMAIL_TOKEN_FILE` | Path to the **authorized user** JSON file (e.g. `gmail_oauth2_token.json`). Relative paths are resolved from the repo root |

**Google Cloud Console — step by step:**

1. Create or select a project.
2. **APIs & Services → Library** → enable **Gmail API**.
3. **APIs & Services → OAuth consent screen** — configure test users if the app is in testing.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   - Use **Web application** (recommended for a fixed redirect), or follow the same redirect rules as in `scripts/setup_gmail_oauth.py`.
5. Under **Authorized redirect URIs**, add exactly:

   `http://localhost:8085/`

   (Include the trailing slash if that is what the script prints — match character-for-character.)

6. Copy **Client ID** and **Client secret** into `.env` as `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`.
7. Set `GMAIL_REDIRECT_URI=http://localhost:8085/` in `.env` to match.

**Create the token file (one-time):**

From the repo root, with `.env` filled:

```bash
python scripts/setup_gmail_oauth.py
```

- A browser opens for Google sign-in.
- After consent, the script writes JSON to `GMAIL_TOKEN_FILE`.
- Ensure the output shows **`refresh_token: present`** for long-lived refresh; if not, revoke app access in your Google Account and run again (see messages printed by the script).

Scope used: `https://mail.google.com/` (full mail access — required by the puller implementation).

---

### 4.3 Gmail app password block — `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_IMAP_*`

These appear in `.env.example` as an **IMAP / app-password** style backup. The main pipeline uses **Gmail OAuth** (`scripts/gmail_puller.py`), not IMAP, for ingestion and drafting.

You may leave these blank unless you add or run tooling that reads them. If you fill them for future use:

- `EMAIL_USERNAME` — full Gmail address  
- `EMAIL_PASSWORD` — [Google App Password](https://support.google.com/accounts/answer/185833) (not your normal login password if 2FA is on)  
- `EMAIL_IMAP_SERVER` — default `imap.gmail.com`  
- `EMAIL_IMAP_PORT` — default `993`  

---

### 4.4 JWT — `JWT_SECRET_KEY`, `JWT_ALGORITHM`

Included for API-style authentication defaults (`FastAPI` / `python-jose` are in `requirements.txt`). Set a **long random** `JWT_SECRET_KEY` in production (not `test123`).

If you only run `scripts/run_pipeline.py` and related scripts, these may be unused until you expose an API that validates JWTs — still good practice to set a real secret.

---

### 4.5 Logging — `LOG_LEVEL`, `LOG_FORMAT`

| Variable | Typical values |
|----------|------------------|
| `LOG_LEVEL` | `INFO`, `DEBUG`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `console` (structured logging may use other modes depending on app wiring) |

---

### 4.6 LLM — `LLM_BASE_URL`, `LLM_MODEL`, timeouts and concurrency

The LLM client (`src/llm/client.py`) expects an **OpenAI-compatible** HTTP API: **`POST`** to a URL whose path is typically **`/v1/chat/completions`**, with JSON body containing `model` and `messages`.

| Variable | Purpose |
|----------|---------|
| `LLM_BASE_URL` | Full URL to the chat completions endpoint (example in `.env.example`: `https://llm.example.com/v1/chat/completions`) |
| `LLM_MODEL` | Model name passed in the request body |
| `LLM_TIMEOUT_S` | HTTP timeout in seconds |
| `LLM_MAX_CONNECTIONS` | `httpx` pool limit |
| `LLM_MAX_KEEPALIVE_CONNECTIONS` | Keep-alive pool size |
| `LLM_MAX_CONCURRENCY` | Semaphore limit for concurrent LLM calls |

Replace the example URL with **your** gateway; ensure the server is reachable from the machine running the pipeline and that the model name matches what that server expects.

---

## 5. Run database migrations

Alembic configuration lives under `src/db/` (`alembic.ini` + `migrations/`).

From the **`src/db`** directory (adjust path to your clone):

```bash
cd src/db
alembic upgrade head
```

This applies SQLAlchemy migrations using `DATABASE_URL` from your `.env`.

---

## 6. Optional environment variables (not in `.env.example`)

The following exist in `src/utils/config.py` and improve reply quality and signatures:

| Variables | Purpose |
|-----------|---------|
| `COMPANY_NAME`, `COMPANY_WEBSITE`, `LINKEDIN_URL` | Company context |
| `RECRUITER_NAME`, `RECRUITER_EMAIL`, `RECRUITER_TITLE` | Footer / sender display (draft path uses Gmail account email when available) |
| `WORK_LOCATION`, `SALARY_SENIOR` | Role / location messaging |
| `SMTP_*` | SMTP is optional; outbound drafts use **Gmail API** via OAuth |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | LangSmith tracing |
| `REDIS_URL` | Reserved if you add caching / queues |
| `SLACK_WEBHOOK_URL` | Notifications |

Add them to `.env` as needed.

---

## 7. Run the email replier pipeline

Main entry point: `scripts/run_pipeline.py`.

**Examples** (from repo root, virtualenv active):

```bash
# Full run: Gmail pull → DB → agents → draft reply (default limit 50)
python scripts/run_pipeline.py

# Limit processed emails
python scripts/run_pipeline.py --limit 10

# Skip Gmail pull; only process pending rows already in PostgreSQL
python scripts/run_pipeline.py --skip-pull

# Poll every 60 seconds until Ctrl+C
python scripts/run_pipeline.py --monitor
```

**Windows note:** The pipeline forces a **selector** asyncio policy on Windows where needed for database drivers — this is already handled in code.

---

## 8. Verify setup quickly

1. **Database:** `alembic upgrade head` succeeds; you can connect with `psql` or a GUI using the same credentials as in `DATABASE_URL`.
2. **Gmail:** `gmail_oauth2_token.json` (or your `GMAIL_TOKEN_FILE`) exists and `setup_gmail_oauth.py` reported a refresh token.
3. **LLM:** Run a small pipeline or unit script that calls the LLM; fix URL/model/firewall if requests fail.
4. **End-to-end:** `python scripts/run_pipeline.py --limit 1` and confirm a draft appears in Gmail Drafts (the app creates **drafts**, not sent mail).

---

## 9. Troubleshooting

| Issue | What to check |
|-------|----------------|
| `Token file not found` | Run `python scripts/setup_gmail_oauth.py`; confirm `GMAIL_TOKEN_FILE` path |
| Redirect URI mismatch | Google Cloud redirect must **exactly** match `http://localhost:8085/` (or whatever host/port you configured) |
| Database connection errors | `DATABASE_URL`, Postgres running, database created, firewall, credentials |
| Wrong DB host after editing `.env` | Config guardrail may rewrite a specific legacy IP; verify `src/utils/config.py` |
| `gen_random_uuid` / extension errors | Run `CREATE EXTENSION pgcrypto;` on your database |
| LLM timeouts or empty replies | Increase `LLM_TIMEOUT_S`; verify `LLM_BASE_URL` and model; check server logs |

---

## 10. Files you should expect after setup

- **`.env`** — local secrets (not committed).
- **`gmail_oauth2_token.json`** (or your chosen `GMAIL_TOKEN_FILE`) — OAuth token JSON beside the project or at an absolute path you configured.
- **`data/`** — runtime data such as `replies.json` / `logs.json` when used by the app.

You are then ready to run and iterate on `python scripts/run_pipeline.py` with the options that match your workflow.
