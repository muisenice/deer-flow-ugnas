# UGreen NAS Compose Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the official production `docker/docker-compose.yaml` deployment path work cleanly on `x86_64` UGreen NAS with `LocalSandboxProvider`, while keeping future upstream upgrades low-drift.

**Architecture:** Refactor `scripts/deploy.sh` into a source-safe helper-based bootstrapper that seeds missing runtime files and prepares optional CLI bind directories. Parameterize the production Compose bind mounts so they no longer depend on `${HOME}`, then add a focused NAS deployment guide that teaches operators to keep local state in config/data paths rather than maintaining a forked Compose file.

**Tech Stack:** Bash, Docker Compose, Pytest, Markdown documentation

---

## File Structure

- `scripts/deploy.sh`
  - Add a `main()` entrypoint guard so tests can `source` the script without launching Docker.
  - Add helper functions for seeding runtime files and preparing optional CLI config directories.
  - Export deterministic defaults for `DEER_FLOW_CLAUDE_CONFIG_DIR` and `DEER_FLOW_CODEX_CONFIG_DIR`.
- `docker/docker-compose.yaml`
  - Replace `${HOME}/.claude` and `${HOME}/.codex` bind mounts with explicit env-driven host paths.
  - Update comments so the production Compose file documents the new variables.
- `backend/tests/test_deploy_script.py`
  - New regression coverage for `deploy.sh` helper functions and exported default directory behavior.
- `backend/tests/test_gateway_runtime_cleanup.py`
  - Extend static coverage to ensure production Compose no longer requires `${HOME}` for CLI config binds.
- `backend/docs/UGREEN_NAS.md`
  - New Chinese deployment guide for UGreen NAS using the official production Compose flow.
- `backend/docs/README.md`
  - Add a quick link to the NAS deployment guide.
- `README_zh.md`
  - Link the NAS guide from the Docker production section so operators can find it before editing Compose.

### Task 1: Make `deploy.sh` Source-Safe and Seed Runtime Env Files

**Files:**
- Create: `backend/tests/test_deploy_script.py`
- Modify: `scripts/deploy.sh`
- Test: `backend/tests/test_deploy_script.py`

- [ ] **Step 1: Write the failing deploy bootstrap tests**

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy.sh"
BASH_CANDIDATES = [
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(which("bash")) if which("bash") else None,
]
BASH_EXECUTABLE = next(
    (
        str(path)
        for path in BASH_CANDIDATES
        if path is not None and path.exists() and "WindowsApps" not in str(path)
    ),
    None,
)

if BASH_EXECUTABLE is None:
    pytestmark = pytest.mark.skip(reason="bash is required for deploy.sh tests")


def _bash(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH_EXECUTABLE, "-lc", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_seed_file_if_missing_copies_template(tmp_path):
    src = tmp_path / ".env.example"
    dst = tmp_path / ".env"
    src.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")

    result = _bash(
        f"source '{SCRIPT_PATH}' && "
        f"seed_file_if_missing '{src}' '{dst}' '.env'"
    )

    assert result.returncode == 0
    assert dst.read_text(encoding='utf-8') == "OPENAI_API_KEY=test-key\n"


def test_seed_file_if_missing_does_not_overwrite_existing_file(tmp_path):
    src = tmp_path / "frontend.env.example"
    dst = tmp_path / "frontend.env"
    src.write_text("NEXT_PUBLIC_BACKEND_BASE_URL=http://example.test\n", encoding="utf-8")
    dst.write_text("KEEP_ME=1\n", encoding="utf-8")

    result = _bash(
        f"source '{SCRIPT_PATH}' && "
        f"seed_file_if_missing '{src}' '{dst}' 'frontend/.env'"
    )

    assert result.returncode == 0
    assert dst.read_text(encoding='utf-8') == "KEEP_ME=1\n"


def test_seed_file_if_missing_creates_parent_directory(tmp_path):
    src = tmp_path / "frontend.env.example"
    dst = tmp_path / "frontend" / ".env"
    src.write_text("NEXT_PUBLIC_FLAG=1\n", encoding="utf-8")

    result = _bash(
        f"source '{SCRIPT_PATH}' && "
        f"seed_file_if_missing '{src}' '{dst}' 'frontend/.env'"
    )

    assert result.returncode == 0
    assert dst.read_text(encoding='utf-8') == "NEXT_PUBLIC_FLAG=1\n"
```

- [ ] **Step 2: Run the deploy bootstrap tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_deploy_script.py -q
```

Expected: FAIL because `scripts/deploy.sh` is not source-safe yet and `seed_file_if_missing` does not exist.

- [ ] **Step 3: Refactor `scripts/deploy.sh` to add reusable file-seeding helpers**

```bash
seed_file_if_missing() {
    local src="$1"
    local dst="$2"
    local label="$3"

    if [ -f "$dst" ]; then
        echo -e "${GREEN}✓ ${label}: $dst${NC}"
        return 0
    fi

    if [ ! -f "$src" ]; then
        echo -e "${RED}✗ Missing template for ${label}: $src${NC}"
        return 1
    fi

    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo -e "${GREEN}✓ Seeded $(basename "$src") → $dst${NC}"
}


prepare_runtime_files() {
    seed_file_if_missing "$REPO_ROOT/config.example.yaml" "$DEER_FLOW_CONFIG_PATH" "config.yaml"
    seed_file_if_missing "$REPO_ROOT/.env.example" "$REPO_ROOT/.env" ".env"
    seed_file_if_missing "$REPO_ROOT/frontend/.env.example" "$REPO_ROOT/frontend/.env" "frontend/.env"
}


main() {
    parse_args "$@"
    # existing deploy flow here
}


if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
```

Implementation notes:

- Keep the existing `config.yaml` and `extensions_config.json` behavior, but move it behind helper-driven flow so the script can be sourced in tests.
- Preserve current user-facing success/error messages where possible.
- Do not overwrite existing `.env` or `frontend/.env`.

- [ ] **Step 4: Extend `prepare_runtime_files()` to create `frontend/.env` during production bootstrap**

```bash
if [ -z "$DEER_FLOW_CONFIG_PATH" ]; then
    export DEER_FLOW_CONFIG_PATH="$REPO_ROOT/config.yaml"
fi
if [ -z "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
    export DEER_FLOW_EXTENSIONS_CONFIG_PATH="$REPO_ROOT/extensions_config.json"
fi

prepare_runtime_files

if [ ! -f "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
    echo '{"mcpServers":{},"skills":{}}' > "$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
    echo -e "${YELLOW}⚠ extensions_config.json not found, created empty config at $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
fi
```

- [ ] **Step 5: Run the deploy bootstrap tests to verify they pass**

Run:

```bash
cd backend && uv run pytest tests/test_deploy_script.py -q
```

Expected: PASS with three passing tests for template seeding and non-overwrite behavior.

- [ ] **Step 6: Commit the deploy bootstrap refactor**

```bash
git add scripts/deploy.sh backend/tests/test_deploy_script.py
git commit -m "chore: harden production deploy bootstrap"
```

### Task 2: Parameterize Optional CLI Config Mounts for Production Compose

**Files:**
- Modify: `scripts/deploy.sh`
- Modify: `docker/docker-compose.yaml`
- Modify: `backend/tests/test_deploy_script.py`
- Modify: `backend/tests/test_gateway_runtime_cleanup.py`
- Test: `backend/tests/test_deploy_script.py`
- Test: `backend/tests/test_gateway_runtime_cleanup.py`

- [ ] **Step 1: Add failing tests for default CLI config directories and HOME-free Compose mounts**

```python
def test_set_default_cli_config_dirs_uses_deer_flow_home(tmp_path):
    deer_flow_home = tmp_path / "runtime"
    result = _bash(
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"source '{SCRIPT_PATH}' && "
        "set_default_cli_config_dirs && "
        'printf "%s\\n%s" "$DEER_FLOW_CLAUDE_CONFIG_DIR" "$DEER_FLOW_CODEX_CONFIG_DIR"'
    )

    assert result.returncode == 0
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines == [
        str(deer_flow_home / "cli-config" / ".claude"),
        str(deer_flow_home / "cli-config" / ".codex"),
    ]
    assert (deer_flow_home / "cli-config" / ".claude").is_dir()
    assert (deer_flow_home / "cli-config" / ".codex").is_dir()
```

```python
def test_production_compose_uses_explicit_cli_config_env_vars():
    content = _read("docker/docker-compose.yaml")

    assert "${HOME:?HOME must be set}/.claude" not in content
    assert "${HOME:?HOME must be set}/.codex" not in content
    assert "DEER_FLOW_CLAUDE_CONFIG_DIR" in content
    assert "DEER_FLOW_CODEX_CONFIG_DIR" in content
```

- [ ] **Step 2: Run the focused regression tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_deploy_script.py tests/test_gateway_runtime_cleanup.py -q
```

Expected: FAIL because `set_default_cli_config_dirs` does not exist and `docker/docker-compose.yaml` still references `${HOME}`.

- [ ] **Step 3: Export deterministic CLI config directory defaults in `scripts/deploy.sh`**

```bash
set_default_cli_config_dirs() {
    if [ -z "${DEER_FLOW_CLAUDE_CONFIG_DIR:-}" ]; then
        export DEER_FLOW_CLAUDE_CONFIG_DIR="$DEER_FLOW_HOME/cli-config/.claude"
    fi
    if [ -z "${DEER_FLOW_CODEX_CONFIG_DIR:-}" ]; then
        export DEER_FLOW_CODEX_CONFIG_DIR="$DEER_FLOW_HOME/cli-config/.codex"
    fi

    mkdir -p "$DEER_FLOW_CLAUDE_CONFIG_DIR" "$DEER_FLOW_CODEX_CONFIG_DIR"
}


if [ "$CMD" = "down" ]; then
    export DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_ROOT/backend/.deer-flow}"
    set_default_cli_config_dirs
    export DEER_FLOW_CLAUDE_CONFIG_DIR
    export DEER_FLOW_CODEX_CONFIG_DIR
    "${COMPOSE_CMD[@]}" down
    exit 0
fi
```

Implementation notes:

- Call `set_default_cli_config_dirs` before `docker compose build`, `up`, and `down` so parse-time env resolution always has values.
- Keep the directories under `DEER_FLOW_HOME` to avoid leaking local machine semantics into production deploys.

- [ ] **Step 4: Replace `${HOME}`-based binds in `docker/docker-compose.yaml`**

```yaml
      # Optional CLI auth directories for Claude Code / Codex ACP integrations.
      # Defaults are prepared by scripts/deploy.sh under ${DEER_FLOW_HOME}/cli-config/.
      - type: bind
        source: ${DEER_FLOW_CLAUDE_CONFIG_DIR}
        target: /root/.claude
        read_only: true
        bind:
          create_host_path: true
      - type: bind
        source: ${DEER_FLOW_CODEX_CONFIG_DIR}
        target: /root/.codex
        read_only: true
        bind:
          create_host_path: true
```

Also update the Compose header comment block to list:

```yaml
#   DEER_FLOW_CLAUDE_CONFIG_DIR      — optional host dir for /root/.claude
#   DEER_FLOW_CODEX_CONFIG_DIR       — optional host dir for /root/.codex
```

- [ ] **Step 5: Run the focused regression tests to verify they pass**

Run:

```bash
cd backend && uv run pytest tests/test_deploy_script.py tests/test_gateway_runtime_cleanup.py -q
```

Expected: PASS with `deploy.sh` helper coverage green and static assertions confirming Compose no longer depends on `${HOME}`.

- [ ] **Step 6: Sanity-check production Compose parsing with local-sandbox defaults**

Run:

```bash
bash -lc 'source scripts/deploy.sh && DEER_FLOW_HOME="$PWD/backend/.deer-flow" && CMD=down && set_default_cli_config_dirs && docker compose -p deer-flow -f docker/docker-compose.yaml config > /tmp/deer-flow-compose.yaml'
```

Expected: command exits `0` and writes a rendered Compose file without `${HOME}` resolution errors.

- [ ] **Step 7: Commit the production Compose parameterization**

```bash
git add scripts/deploy.sh docker/docker-compose.yaml backend/tests/test_deploy_script.py backend/tests/test_gateway_runtime_cleanup.py
git commit -m "feat: parameterize production cli config mounts"
```

### Task 3: Publish the UGreen NAS Deployment Guide and Link It from Existing Docs

**Files:**
- Create: `backend/docs/UGREEN_NAS.md`
- Modify: `backend/docs/README.md`
- Modify: `README_zh.md`
- Test: `backend/docs/UGREEN_NAS.md`
- Test: `README_zh.md`

- [ ] **Step 1: Draft the NAS guide content as a failing docs diff**

````md
# UGreen NAS Docker Compose Deployment

## Scope

- `x86_64 / Intel` UGreen NAS
- LAN-only access
- `sandbox.use: deerflow.sandbox.local:LocalSandboxProvider`
- Official production entrypoint: `docker/docker-compose.yaml` + `scripts/deploy.sh`

## Recommended host paths

- Repo checkout: `/mnt/data/deer-flow/repo`
- Runtime data: `/mnt/data/deer-flow/runtime`
- Optional CLI config overrides:
  - `/mnt/data/deer-flow/runtime/cli-config/.claude`
  - `/mnt/data/deer-flow/runtime/cli-config/.codex`

## First boot

```bash
cd /mnt/data/deer-flow/repo
cp config.example.yaml config.yaml
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Edit `config.yaml` so the sandbox section stays on:

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: false
```

Then start DeerFlow:

```bash
export DEER_FLOW_HOME=/mnt/data/deer-flow/runtime
bash scripts/deploy.sh
```
````

- [ ] **Step 2: Add the final NAS guide and doc links**

```md
| [UGREEN_NAS.md](UGREEN_NAS.md) | UGreen NAS deployment using the official production Compose flow |
```

```md
如果你要在绿联云 NAS 上使用官方生产 Compose 部署，并且希望后续更容易跟进上游更新，参见 [UGreen NAS 部署指南](backend/docs/UGREEN_NAS.md)。
```

Implementation notes:

- Keep the guide focused on operational steps, not development mode.
- Explain that future upgrades should preserve `config.yaml`, `.env`, `frontend/.env`, and `DEER_FLOW_HOME`, then rebuild from upstream.
- Do not introduce a second Compose file in the docs.

- [ ] **Step 3: Run a docs consistency pass**

Run:

```bash
Select-String -Path backend/docs/UGREEN_NAS.md,backend/docs/README.md,README_zh.md -Pattern 'docker-compose.nas|HOME must be set|公网反向代理'
```

Expected: no matches, confirming the new docs do not introduce a forked Compose path or reintroduce `${HOME}` guidance.

- [ ] **Step 4: Run the regression tests one more time after the docs link updates**

Run:

```bash
cd backend && uv run pytest tests/test_deploy_script.py tests/test_gateway_runtime_cleanup.py -q
```

Expected: PASS, confirming the documentation edits did not require code follow-ups.

- [ ] **Step 5: Commit the NAS documentation**

```bash
git add backend/docs/UGREEN_NAS.md backend/docs/README.md README_zh.md
git commit -m "docs: add ugreen nas deployment guide"
```

## Self-Review

- Spec coverage:
  - Missing `.env` and `frontend/.env` bootstrap: Task 1
  - Optional CLI config mount parameterization: Task 2
  - NAS deployment guide and upstream-friendly upgrade flow: Task 3
- Placeholder scan:
  - No `TODO`, `TBD`, or “implement later” markers remain in the plan.
  - Every command-producing step includes an explicit command block.
- Type consistency:
  - Helper names are consistent across tasks: `seed_file_if_missing`, `prepare_runtime_files`, `set_default_cli_config_dirs`.
