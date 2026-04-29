# UGreen NAS Deployment Guide

This guide is for x86_64 / Intel-based UGreen NAS devices running DeerFlow on a trusted LAN. It stays on the official production deployment path:

- `docker/docker-compose.yaml`
- `scripts/deploy.sh`

Do not create or maintain a separate NAS-specific compose file. Keeping the upstream compose file and deployment script unchanged makes future upgrades much easier.

## Scope and assumptions

- NAS CPU architecture: `x86_64` / Intel
- Access model: LAN-only access for trusted users and devices
- Sandbox mode: `deerflow.sandbox.local:LocalSandboxProvider`
- Deployment mode: production Docker Compose via `./scripts/deploy.sh`

If you need public internet exposure, extra reverse proxies, or a custom compose fork, that is outside the scope of this guide.

## Recommended directory layout

Keep the Git checkout and runtime data on persistent NAS storage.

```text
/volume1/docker/deer-flow/
├── repo/                     # git clone https://github.com/bytedance/deer-flow.git
└── data/
    └── deer-flow-home/       # exported as DEER_FLOW_HOME
```

Recommended runtime paths:

- Repo root: `/volume1/docker/deer-flow/repo`
- `DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home`
- `DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml` (optional override)
- `DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json` (optional override)

Why this layout:

- The Git checkout can be updated in place with `git pull`.
- Runtime files survive container rebuilds and repo refreshes.
- `deploy.sh` defaults CLI config directories under `DEER_FLOW_HOME/cli-config/`, so you usually do not need to mount extra Claude/Codex config paths manually.

## Before first boot

1. Clone the repo onto the NAS persistent volume.
2. Install Docker and Docker Compose support provided by the NAS OS.
3. Open a shell in the repo root.
4. Export a persistent runtime home before running production deploy commands.

Example:

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
./scripts/deploy.sh
```

`deploy.sh` is the official production entrypoint. It invokes `docker compose -f docker/docker-compose.yaml ...` and prepares the runtime files that the stack expects.

## First boot behavior

On the first run, `./scripts/deploy.sh` will:

- create `DEER_FLOW_HOME` if it does not exist
- seed `config.yaml` if `DEER_FLOW_CONFIG_PATH` does not already exist
- seed `.env` from `.env.example` if the repo root `.env` is missing
- seed `frontend/.env` from `frontend/.env.example` if it is missing
- create `extensions_config.json` when needed
- create default CLI config directories under `DEER_FLOW_HOME/cli-config/`
- generate and persist `BETTER_AUTH_SECRET` under `DEER_FLOW_HOME`

After the first boot, stop and review the generated files before treating the deployment as ready for daily use.

## Required config expectations

### `config.yaml`

For this NAS guide, keep the sandbox on `LocalSandboxProvider`.

Minimal expectation:

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
```

Also configure at least one working model in `config.yaml` before real use.

### Root `.env`

The production compose file loads the repo root `.env` into the `gateway` container. Put provider keys and optional tracing settings here, for example:

```bash
OPENAI_API_KEY=your-openai-api-key
TAVILY_API_KEY=your-tavily-api-key
```

### `frontend/.env`

The production compose file also loads `frontend/.env` into the frontend container. Keep this file present even if you only use the seeded defaults.

## LAN-only access guidance

This guide assumes DeerFlow stays inside a trusted LAN.

- Only publish the DeerFlow port to your local network.
- Do not expose the service directly to the public internet.
- Prefer NAS firewall or router rules that limit access to trusted clients.
- If you need broader exposure later, start from the upstream security guidance first instead of changing to a custom NAS compose file.

## Start and stop

One-step deploy:

```bash
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
./scripts/deploy.sh
```

Build once, start later:

```bash
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
./scripts/deploy.sh build
./scripts/deploy.sh start
```

Stop:

```bash
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
./scripts/deploy.sh down
```

## Notes about CLI config mounts

The production stack includes bind mounts for Claude Code and Codex auth directories, but you usually do not need to manage them yourself on a NAS.

- `deploy.sh` defaults `DEER_FLOW_CLAUDE_CONFIG_DIR` to `$DEER_FLOW_HOME/cli-config/.claude`
- `deploy.sh` defaults `DEER_FLOW_CODEX_CONFIG_DIR` to `$DEER_FLOW_HOME/cli-config/.codex`

If you do not override those variables, the directories live under `DEER_FLOW_HOME` automatically and remain persistent with the rest of the runtime data.

## Upgrade path

To keep upgrades close to upstream, preserve the runtime files and continue using the same official compose path.

1. Keep the same `DEER_FLOW_HOME`.
2. Preserve these files across upgrades:
   - `config.yaml`
   - `.env`
   - `frontend/.env`
   - everything already stored under `DEER_FLOW_HOME`
3. Update the Git checkout.
4. Re-run the official deploy script.

Example:

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
git pull --ff-only
./scripts/deploy.sh build
./scripts/deploy.sh start
```

Because your persistent config and runtime data stay outside the containers, image rebuilds do not wipe the deployment state.

## Troubleshooting checklist

- If DeerFlow seeds a fresh `config.yaml`, edit it before production use and confirm it still points to `LocalSandboxProvider`.
- If you move the repo checkout, keep `DEER_FLOW_HOME` stable so runtime data is not split across locations.
- If the NAS shell session forgets exported variables, define `DEER_FLOW_HOME` in the shell profile or your NAS task runner before calling `deploy.sh`.
- If you need custom behavior, prefer environment overrides supported by `deploy.sh` over copying `docker/docker-compose.yaml`.
