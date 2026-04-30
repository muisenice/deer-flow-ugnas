"""Process-local authentication for Gateway internal callers."""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path
from types import SimpleNamespace

from deerflow.runtime.user_context import DEFAULT_USER_ID

INTERNAL_AUTH_HEADER_NAME = "X-DeerFlow-Internal-Token"
_INTERNAL_AUTH_TOKEN_ENV = "DEER_FLOW_INTERNAL_AUTH_TOKEN"
_INTERNAL_AUTH_TOKEN_FILE_ENV = "DEER_FLOW_INTERNAL_AUTH_TOKEN_FILE"


def _internal_auth_token_file() -> Path:
    configured = os.getenv(_INTERNAL_AUTH_TOKEN_FILE_ENV, "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "deerflow-internal-auth-token"


def _load_or_create_shared_internal_auth_token() -> str:
    configured = os.getenv(_INTERNAL_AUTH_TOKEN_ENV, "").strip()
    if configured:
        return configured

    token_path = _internal_auth_token_file()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        existing = token_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""

    if existing:
        return existing

    token = secrets.token_urlsafe(32)
    try:
        with token_path.open("x", encoding="utf-8") as f:
            f.write(token)
        return token
    except FileExistsError:
        existing = token_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
        token_path.write_text(token, encoding="utf-8")
        return token


_INTERNAL_AUTH_TOKEN = _load_or_create_shared_internal_auth_token()


def create_internal_auth_headers() -> dict[str, str]:
    """Return headers that authenticate same-process Gateway internal calls."""
    return {INTERNAL_AUTH_HEADER_NAME: _INTERNAL_AUTH_TOKEN}


def is_valid_internal_auth_token(token: str | None) -> bool:
    """Return True when *token* matches the process-local internal token."""
    return bool(token) and secrets.compare_digest(token, _INTERNAL_AUTH_TOKEN)


def get_internal_user():
    """Return the synthetic user used for trusted internal channel calls."""
    return SimpleNamespace(id=DEFAULT_USER_ID, system_role="internal")
