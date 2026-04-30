"""Regression coverage for the Gateway-owned LangGraph API runtime."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_root_makefile_no_longer_exposes_transition_gateway_targets():
    makefile = _read("Makefile")

    assert "dev-pro" not in makefile
    assert "start-pro" not in makefile
    assert "dev-daemon-pro" not in makefile
    assert "start-daemon-pro" not in makefile
    assert "docker-start-pro" not in makefile
    assert "up-pro" not in makefile
    assert not re.search(r"serve\.sh .*--gateway", makefile)
    assert "docker.sh start --gateway" not in makefile
    assert "deploy.sh --gateway" not in makefile


def test_service_launchers_always_use_gateway_runtime():
    operational_files = {
        "scripts/serve.sh": _read("scripts/serve.sh"),
        "scripts/docker.sh": _read("scripts/docker.sh"),
        "scripts/deploy.sh": _read("scripts/deploy.sh"),
        "docker/docker-compose-dev.yaml": _read("docker/docker-compose-dev.yaml"),
        "docker/docker-compose.yaml": _read("docker/docker-compose.yaml"),
    }

    for path, content in operational_files.items():
        assert "start --gateway" not in content, path
        assert "deploy.sh --gateway" not in content, path
        assert "langgraph dev" not in content, path
        assert "LANGGRAPH_UPSTREAM" not in content, path
        assert "LANGGRAPH_REWRITE" not in content, path


def test_nginx_routes_official_langgraph_prefix_to_gateway_api():
    for path in ("docker/nginx/nginx.local.conf", "docker/nginx/nginx.conf"):
        content = _read(path)

        assert "/api/langgraph-compat" not in content
        assert "proxy_pass http://langgraph" not in content
        assert "rewrite ^/api/langgraph/(.*) /api/$1 break;" in content
        assert "proxy_pass http://gateway" in content


def test_frontend_rewrites_langgraph_prefix_to_gateway():
    next_config = _read("frontend/next.config.js")
    api_client = _read("frontend/src/core/api/api-client.ts")

    assert "DEER_FLOW_INTERNAL_LANGGRAPH_BASE_URL" not in next_config
    assert "http://127.0.0.1:2024" not in next_config
    assert "langgraph-compat" not in api_client


def test_production_compose_uses_deer_flow_cli_config_mounts_instead_of_home():
    compose = _read("docker/docker-compose.yaml")

    assert "${HOME:?HOME must be set}/.claude" not in compose
    assert "${HOME:?HOME must be set}/.codex" not in compose
    assert "${DEER_FLOW_CLAUDE_CONFIG_DIR:?" in compose
    assert "${DEER_FLOW_CODEX_CONFIG_DIR:?" in compose


def test_production_compose_requires_cli_config_env_vars_at_parse_time():
    compose = _read("docker/docker-compose.yaml")

    assert "source: ${DEER_FLOW_CLAUDE_CONFIG_DIR:?DEER_FLOW_CLAUDE_CONFIG_DIR must be set}" in compose
    assert "source: ${DEER_FLOW_CODEX_CONFIG_DIR:?DEER_FLOW_CODEX_CONFIG_DIR must be set}" in compose


def test_production_compose_passes_frontend_auth_runtime_env():
    compose = _read("docker/docker-compose.yaml")

    assert "- BETTER_AUTH_URL=${BETTER_AUTH_URL:-}" in compose
    assert "- DEER_FLOW_TRUSTED_ORIGINS=${DEER_FLOW_TRUSTED_ORIGINS:-}" in compose


def test_frontend_memory_routes_prefer_internal_gateway_env():
    memory_route = _read("frontend/src/app/api/memory/route.ts")
    memory_nested_route = _read("frontend/src/app/api/memory/[...path]/route.ts")

    for content in (memory_route, memory_nested_route):
        assert "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL" in content
        assert 'process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? "http://127.0.0.1:8001"' not in content
