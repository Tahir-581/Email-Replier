#!/usr/bin/env python3
"""
One-time Gmail OAuth2 setup: opens a browser, user signs in, saves authorized-user JSON.

Output path: GMAIL_TOKEN_FILE from .env (default token.json), e.g. gmail_oauth2_token.json.

Requires either:
  - --client-secrets PATH   (JSON from Google Cloud Console, OAuth client type "Desktop app"), or
  - GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env (same as Desktop client values).

Scopes match scripts/gmail_puller.py (full mail access).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Project root on path (run: python scripts/setup_gmail_oauth.py from email-replier/)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from src.utils.config import PROJECT_ROOT, settings  # noqa: E402

# Must stay aligned with scripts/gmail_puller.py
SCOPES = ["https://mail.google.com/"]

# Google Cloud "Web application" clients require an *exact* redirect URI match.
# Random ports (run_local_server(port=0)) break that — use a fixed port and register it in GCP.
_DEFAULT_LOOPBACK_HOST = "localhost"
_DEFAULT_LOOPBACK_PORT = 8085


def _loopback_host_port() -> tuple[str, int]:
    raw = (settings.GMAIL_REDIRECT_URI or "").strip()
    if not raw or "accounts.google.com" in raw:
        return _DEFAULT_LOOPBACK_HOST, _DEFAULT_LOOPBACK_PORT
    parsed = urlparse(raw)
    if parsed.scheme != "http":
        return _DEFAULT_LOOPBACK_HOST, _DEFAULT_LOOPBACK_PORT
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        return _DEFAULT_LOOPBACK_HOST, _DEFAULT_LOOPBACK_PORT
    host = parsed.hostname or _DEFAULT_LOOPBACK_HOST
    port = parsed.port if parsed.port is not None else _DEFAULT_LOOPBACK_PORT
    if port <= 0:
        return _DEFAULT_LOOPBACK_HOST, _DEFAULT_LOOPBACK_PORT
    return host, port


def _out_path() -> Path:
    p = Path(settings.GMAIL_TOKEN_FILE)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _flow_from_secrets_file(path: Path) -> InstalledAppFlow:
    return InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)


def _flow_from_env() -> InstalledAppFlow:
    cid = (settings.GMAIL_CLIENT_ID or "").strip()
    sec = (settings.GMAIL_CLIENT_SECRET or "").strip()
    if not cid or not sec:
        raise SystemExit(
            "Missing GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET in .env, "
            "or pass --client-secrets /path/to/client_secret....json"
        )
    cfg = {
        "installed": {
            "client_id": cid,
            "client_secret": sec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }
    return InstalledAppFlow.from_client_config(cfg, SCOPES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Gmail OAuth token file (authorized user JSON).")
    parser.add_argument(
        "--client-secrets",
        type=Path,
        help="OAuth client JSON from Google Cloud (Desktop app client)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Local callback port (default: from GMAIL_REDIRECT_URI or {_DEFAULT_LOOPBACK_PORT}). Must match Google Cloud redirect URI.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help=f"Local callback host (default: from GMAIL_REDIRECT_URI or {_DEFAULT_LOOPBACK_HOST}).",
    )
    args = parser.parse_args()

    if args.client_secrets:
        if not args.client_secrets.is_file():
            raise SystemExit(f"Not a file: {args.client_secrets}")
        flow = _flow_from_secrets_file(args.client_secrets)
    else:
        flow = _flow_from_env()

    host, port = _loopback_host_port()
    if args.host is not None:
        host = args.host
    if args.port is not None:
        port = args.port
    redirect_uri = f"http://{host}:{port}/"
    print(
        "Register this exact URI under Google Cloud Console → APIs & Services → Credentials → "
        f"your OAuth client → Authorized redirect URIs:\n  {redirect_uri}\n"
        "(Web client: required. Desktop client: use Desktop type or same redirect list.)\n"
    )

    creds = flow.run_local_server(
        host=host,
        port=port,
        open_browser=True,
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    out = _out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(creds.to_json(), encoding="utf-8")
    print(f"Wrote token to {out}")
    data = json.loads(creds.to_json())
    if data.get("refresh_token"):
        print("refresh_token: present (good for long-running use)")
    else:
        print(
            "Warning: no refresh_token. If this account was used before, "
            "revoke app access in Google Account settings and run again, "
            "or use prompt='consent' / access_type in a custom flow."
        )


if __name__ == "__main__":
    main()
