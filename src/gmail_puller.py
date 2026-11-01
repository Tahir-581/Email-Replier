"""Compatibility wrapper for Gmail pulling/sending.

The original implementation lives in `scripts/gmail_puller.py`. Importing it as
`scripts.gmail_puller` can break if a third-party PyPI package named `scripts`
is installed in the environment. This module loads the local file by path and
re-exports its public API.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast


def _load_local_scripts_gmail_puller() -> ModuleType:
    repo_root = Path(__file__).resolve().parent.parent
    module_path = repo_root / "scripts" / "gmail_puller.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Expected local module at {module_path}")

    spec = importlib.util.spec_from_file_location("_local_scripts_gmail_puller", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {module_path}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MOD = _load_local_scripts_gmail_puller()

# Re-export the main entrypoint used throughout the app.
get_gmail_puller = cast(Any, getattr(_MOD, "get_gmail_puller"))

