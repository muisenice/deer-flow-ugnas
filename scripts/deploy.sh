#!/usr/bin/env bash
#
# deploy.sh - Build, start, or stop DeerFlow production services
#
# Commands:
#   deploy.sh                    - build + start
#   deploy.sh build              - build all images (mode-agnostic)
#   deploy.sh start              - start from pre-built images
#   deploy.sh down               - stop and remove containers
#
# Sandbox mode (local / aio / provisioner) is auto-detected from config.yaml.
#
# Examples:
#   deploy.sh                    # build + start
#   deploy.sh build              # build all images
#   deploy.sh start              # start pre-built images
#   deploy.sh down               # stop and remove containers
#
# Must be run from the repo root directory.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_DIR="$REPO_ROOT/docker"
COMPOSE_CMD=(docker compose -p deer-flow -f "$DOCKER_DIR/docker-compose.yaml")
CMD=""
SEED_FILE_IF_MISSING_STATUS=""

# - Colors --------------------------------------------------------------------

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

parse_args() {
    case "${1:-}" in
        build|start|down)
            CMD="$1"
            if [ -n "${2:-}" ]; then
                echo "Unknown argument: $2"
                echo "Usage: deploy.sh [build|start|down]"
                return 1
            fi
            ;;
        "")
            CMD=""
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: deploy.sh [build|start|down]"
            return 1
            ;;
    esac
}

seed_file_if_missing() {
    local template_path="$1"
    local destination_path="$2"
    local template_label="${3:-$(basename "$template_path")}"

    if [ -f "$destination_path" ]; then
        SEED_FILE_IF_MISSING_STATUS="exists"
        return 0
    fi

    if [ ! -f "$template_path" ]; then
        SEED_FILE_IF_MISSING_STATUS="missing-template"
        return 1
    fi

    mkdir -p "$(dirname "$destination_path")"
    cp "$template_path" "$destination_path"
    SEED_FILE_IF_MISSING_STATUS="seeded"
    echo -e "${GREEN}✓ Seeded $template_label -> $destination_path${NC}"
}

init_runtime_paths() {
    cd "$REPO_ROOT"

    if [ -z "${DEER_FLOW_HOME:-}" ]; then
        export DEER_FLOW_HOME="$REPO_ROOT/backend/.deer-flow"
    fi
    echo -e "${BLUE}DEER_FLOW_HOME=$DEER_FLOW_HOME${NC}"
    mkdir -p "$DEER_FLOW_HOME"

    export DEER_FLOW_REPO_ROOT="$REPO_ROOT"

    if [ -z "${DEER_FLOW_CONFIG_PATH:-}" ]; then
        export DEER_FLOW_CONFIG_PATH="$REPO_ROOT/config.yaml"
    fi

    if [ -z "${DEER_FLOW_EXTENSIONS_CONFIG_PATH:-}" ]; then
        export DEER_FLOW_EXTENSIONS_CONFIG_PATH="$REPO_ROOT/extensions_config.json"
    fi
}

bootstrap_config_file() {
    if seed_file_if_missing "$REPO_ROOT/config.example.yaml" "$DEER_FLOW_CONFIG_PATH" "config.example.yaml"; then
        if [ "$SEED_FILE_IF_MISSING_STATUS" = "seeded" ]; then
            echo -e "${YELLOW}⚠ config.yaml was seeded from the example template.${NC}"
            echo "  Run 'make setup' to generate a minimal config, or edit $DEER_FLOW_CONFIG_PATH manually before use."
            return 0
        fi
    fi

    if [ -f "$DEER_FLOW_CONFIG_PATH" ]; then
        echo -e "${GREEN}✓ config.yaml: $DEER_FLOW_CONFIG_PATH${NC}"
        return 0
    fi

    echo -e "${RED}✗ No config.yaml found.${NC}"
    echo "  Run 'make setup' from the repo root (recommended),"
    echo "  or 'make config' for the full template, then set the required model API keys."
    return 1
}

bootstrap_runtime_env_files() {
    seed_file_if_missing "$REPO_ROOT/.env.example" "$REPO_ROOT/.env" ".env.example" >/dev/null || true
    seed_file_if_missing "$REPO_ROOT/frontend/.env.example" "$REPO_ROOT/frontend/.env" "frontend/.env.example" >/dev/null || true
}

bootstrap_extensions_config() {
    if [ -f "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" ]; then
        echo -e "${GREEN}✓ extensions_config.json: $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
        return 0
    fi

    if [ "$DEER_FLOW_EXTENSIONS_CONFIG_PATH" != "$REPO_ROOT/extensions_config.json" ] && [ -f "$REPO_ROOT/extensions_config.json" ]; then
        mkdir -p "$(dirname "$DEER_FLOW_EXTENSIONS_CONFIG_PATH")"
        cp "$REPO_ROOT/extensions_config.json" "$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
        echo -e "${GREEN}✓ Seeded extensions_config.json -> $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
    else
        mkdir -p "$(dirname "$DEER_FLOW_EXTENSIONS_CONFIG_PATH")"
        echo '{"mcpServers":{},"skills":{}}' > "$DEER_FLOW_EXTENSIONS_CONFIG_PATH"
        echo -e "${YELLOW}⚠ extensions_config.json not found, created empty config at $DEER_FLOW_EXTENSIONS_CONFIG_PATH${NC}"
    fi
}

bootstrap_runtime_files() {
    bootstrap_config_file
    bootstrap_runtime_env_files
    bootstrap_extensions_config
}

# - BETTER_AUTH_SECRET --------------------------------------------------------
# Required by Next.js in production. Generated once and persisted so auth
# sessions survive container restarts.

ensure_better_auth_secret() {
    local secret_file="$DEER_FLOW_HOME/.better-auth-secret"

    if [ -n "${BETTER_AUTH_SECRET:-}" ]; then
        return 0
    fi

    if [ -f "$secret_file" ]; then
        export BETTER_AUTH_SECRET
        BETTER_AUTH_SECRET="$(cat "$secret_file")"
        echo -e "${GREEN}✓ BETTER_AUTH_SECRET loaded from $secret_file${NC}"
    else
        export BETTER_AUTH_SECRET
        BETTER_AUTH_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        echo "$BETTER_AUTH_SECRET" > "$secret_file"
        chmod 600 "$secret_file"
        echo -e "${GREEN}✓ BETTER_AUTH_SECRET generated -> $secret_file${NC}"
    fi
}

# - detect_sandbox_mode -------------------------------------------------------

detect_sandbox_mode() {
    local sandbox_use=""
    local provisioner_url=""

    [ -f "$DEER_FLOW_CONFIG_PATH" ] || { echo "local"; return; }

    sandbox_use=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*use:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*use:[[:space:]]*/, "", line); print line; exit
        }
    ' "$DEER_FLOW_CONFIG_PATH")

    provisioner_url=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*provisioner_url:[[:space:]]*/ {
            line=$0; sub(/^[[:space:]]*provisioner_url:[[:space:]]*/, "", line); print line; exit
        }
    ' "$DEER_FLOW_CONFIG_PATH")

    if [[ "$sandbox_use" == *"deerflow.community.aio_sandbox:AioSandboxProvider"* ]]; then
        if [ -n "$provisioner_url" ]; then
            echo "provisioner"
        else
            echo "aio"
        fi
    else
        echo "local"
    fi
}

handle_down() {
    export DEER_FLOW_HOME="${DEER_FLOW_HOME:-$REPO_ROOT/backend/.deer-flow}"
    export DEER_FLOW_CONFIG_PATH="${DEER_FLOW_CONFIG_PATH:-$DEER_FLOW_HOME/config.yaml}"
    export DEER_FLOW_EXTENSIONS_CONFIG_PATH="${DEER_FLOW_EXTENSIONS_CONFIG_PATH:-$DEER_FLOW_HOME/extensions_config.json}"
    export DEER_FLOW_DOCKER_SOCKET="${DEER_FLOW_DOCKER_SOCKET:-/var/run/docker.sock}"
    export DEER_FLOW_REPO_ROOT="${DEER_FLOW_REPO_ROOT:-$REPO_ROOT}"
    export BETTER_AUTH_SECRET="${BETTER_AUTH_SECRET:-placeholder}"
    "${COMPOSE_CMD[@]}" down
}

handle_build() {
    echo "=========================================="
    echo "  DeerFlow - Building Images"
    echo "=========================================="
    echo ""

    if [ -z "${DEER_FLOW_DOCKER_SOCKET:-}" ]; then
        export DEER_FLOW_DOCKER_SOCKET="/var/run/docker.sock"
    fi

    "${COMPOSE_CMD[@]}" build

    echo ""
    echo "=========================================="
    echo "  ✓ Images built successfully"
    echo "=========================================="
    echo ""
    echo "  Next: deploy.sh start"
    echo ""
}

handle_start() {
    local sandbox_mode
    local services

    echo "=========================================="
    echo "  DeerFlow Production Deployment"
    echo "=========================================="
    echo ""

    sandbox_mode="$(detect_sandbox_mode)"
    echo -e "${BLUE}Sandbox mode: $sandbox_mode${NC}"
    echo -e "${BLUE}Runtime: Gateway embedded agent runtime${NC}"

    services="frontend gateway nginx"
    if [ "$sandbox_mode" = "provisioner" ]; then
        services="$services provisioner"
    fi

    if [ -z "${DEER_FLOW_DOCKER_SOCKET:-}" ]; then
        export DEER_FLOW_DOCKER_SOCKET="/var/run/docker.sock"
    fi

    if [ "$sandbox_mode" != "local" ]; then
        if [ ! -S "$DEER_FLOW_DOCKER_SOCKET" ]; then
            echo -e "${RED}⚠ Docker socket not found at $DEER_FLOW_DOCKER_SOCKET${NC}"
            echo "  AioSandboxProvider (DooD) will not work."
            return 1
        fi
        echo -e "${GREEN}✓ Docker socket: $DEER_FLOW_DOCKER_SOCKET${NC}"
    fi

    echo ""

    if [ "$CMD" = "start" ]; then
        echo "Starting containers (no rebuild)..."
        echo ""
        # shellcheck disable=SC2086
        "${COMPOSE_CMD[@]}" up -d --remove-orphans $services
    else
        echo "Building images and starting containers..."
        echo ""
        # shellcheck disable=SC2086
        "${COMPOSE_CMD[@]}" up --build -d --remove-orphans $services
    fi

    echo ""
    echo "=========================================="
    echo "  DeerFlow is running!"
    echo "=========================================="
    echo ""
    echo "  🌐 Application: http://localhost:${PORT:-2026}"
    echo "  📡 API Gateway: http://localhost:${PORT:-2026}/api/*"
    echo "  🤖 Runtime:     Gateway embedded"
    echo "  API:            /api/langgraph/* → Gateway"
    echo ""
    echo "  Manage:"
    echo "    make down        — stop and remove containers"
    echo "    make docker-logs — view logs"
    echo ""
}

main() {
    set -e
    parse_args "$@" || exit 1
    init_runtime_paths
    bootstrap_runtime_files || exit 1
    ensure_better_auth_secret

    if [ "$CMD" = "down" ]; then
        handle_down
        exit 0
    fi

    if [ "$CMD" = "build" ]; then
        handle_build
        exit 0
    fi

    handle_start
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
