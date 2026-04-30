"""Tests for shared internal Gateway auth token behavior."""

from __future__ import annotations

import importlib


def test_internal_auth_token_persists_via_shared_file(monkeypatch, tmp_path):
    token_file = tmp_path / "internal-auth-token.txt"
    monkeypatch.delenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("DEER_FLOW_INTERNAL_AUTH_TOKEN_FILE", str(token_file))

    import app.gateway.internal_auth as internal_auth

    module = importlib.reload(internal_auth)
    token_first = module.create_internal_auth_headers()[module.INTERNAL_AUTH_HEADER_NAME]

    module = importlib.reload(internal_auth)
    token_second = module.create_internal_auth_headers()[module.INTERNAL_AUTH_HEADER_NAME]

    assert token_first == token_second
    assert token_file.read_text(encoding="utf-8").strip() == token_first


def test_internal_auth_token_env_override_takes_precedence(monkeypatch, tmp_path):
    token_file = tmp_path / "internal-auth-token.txt"
    monkeypatch.setenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", "fixed-shared-token")
    monkeypatch.setenv("DEER_FLOW_INTERNAL_AUTH_TOKEN_FILE", str(token_file))

    import app.gateway.internal_auth as internal_auth

    module = importlib.reload(internal_auth)
    token = module.create_internal_auth_headers()[module.INTERNAL_AUTH_HEADER_NAME]

    assert token == "fixed-shared-token"
    assert not token_file.exists()
