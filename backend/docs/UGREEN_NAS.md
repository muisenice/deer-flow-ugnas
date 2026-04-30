# UGreen NAS 部署指南

本文档适用于在可信局域网内，由单个可信操作者在 `x86_64 / Intel` 架构的绿联 UGreen NAS 上运行 DeerFlow 的场景。部署路径保持为官方生产方案：

- `docker/docker-compose.yaml`
- `scripts/deploy.sh`

不要额外创建或长期维护一份 NAS 专用 compose 文件。尽量保持上游的 compose 文件和部署脚本不分叉，后续升级会轻松很多。

## 适用范围与前提

- NAS CPU 架构：`x86_64` / Intel
- 使用模式：单用户、自托管，由一个可信操作者使用
- 访问模型：仅在可信 NAS 和可信设备组成的局域网内访问
- Sandbox 模式：`deerflow.sandbox.local:LocalSandboxProvider`
- 部署模式：通过 `./scripts/deploy.sh` 走生产 Docker Compose 部署

这不是一份多用户共享部署指南。如果这台 NAS 会被多人共用，或者你需要比 `LocalSandboxProvider` 更强的隔离能力，请改用 [CONFIGURATION.md](CONFIGURATION.md#sandbox) 中更完整的 sandbox 配置方案，而不是继续使用本文档。

如果你需要公网暴露、额外的反向代理，或者自定义 compose 分支，这些都不在本文档范围内。

## 推荐目录布局

建议把 Git 仓库和运行时数据都放到 NAS 的持久化存储上。

```text
/volume1/docker/deer-flow/
├── repo/                     # git clone https://github.com/bytedance/deer-flow.git
└── data/
    └── deer-flow-home/       # 作为 DEER_FLOW_HOME 导出
```

推荐的运行时路径：

- 仓库根目录：`/volume1/docker/deer-flow/repo`
- `DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home`

这里需要特别注意当前 `deploy.sh` 的默认行为：

- 只导出 `DEER_FLOW_HOME`，并不会把 `config.yaml` 移出仓库目录
- 只导出 `DEER_FLOW_HOME`，也不会把 `extensions_config.json` 移出仓库目录
- 如果没有额外覆盖，`deploy.sh` 默认把 `DEER_FLOW_CONFIG_PATH` 设为 `repo/config.yaml`
- 如果没有额外覆盖，`deploy.sh` 默认把 `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 设为 `repo/extensions_config.json`

如果你希望把配置文件也持久化到仓库外部，可以额外覆盖：

- `DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml`
- `DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json`

之所以推荐这种目录布局，是因为：

- Git 仓库可以直接用 `git pull` 原地更新
- 运行时文件在容器重建或仓库刷新后依然保留
- `deploy.sh` 会把官方的 Claude/Codex 绑定目录固定放到 `DEER_FLOW_HOME/cli-config/` 下
- 首次启动时，如果这些运行时凭据文件还不存在，`deploy.sh` 会把宿主机上已记录的认证文件复制到默认位置，这样不需要修改 compose 文件，已有 CLI 登录状态也能继续使用

## 首次启动前

1. 把仓库 clone 到 NAS 的持久化存储目录
2. 安装 NAS 系统提供的 Docker 和 Docker Compose
3. 在仓库根目录打开 shell
4. 决定 `config.yaml` 和 `extensions_config.json` 是继续留在仓库里，还是移到持久化运行目录
5. 在执行生产部署命令前导出运行时环境变量

示例 A：继续使用仓库根目录中的 `config.yaml` 和 `extensions_config.json`（当前默认行为）

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
./scripts/deploy.sh
```

示例 B：把运行时数据和配置文件都放到仓库外部的持久化目录

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
./scripts/deploy.sh
```
示例 C：运行构建很慢大概率是网络源慢 + NAS 内存压力，这时可以加速镜像源：

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
export BUILDKIT_PROGRESS=plain
export APT_MIRROR=mirrors.aliyun.com
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export NPM_REGISTRY=https://registry.npmmirror.com
./scripts/deploy.sh down
./scripts/deploy.sh
```

`deploy.sh` 是官方生产入口。它内部会调用 `docker compose -f docker/docker-compose.yaml ...`，并准备整个运行栈所需的运行时文件。

## 首次启动时会发生什么

第一次运行 `./scripts/deploy.sh` 时，脚本会：

- 如果 `DEER_FLOW_HOME` 不存在，则创建它
- 如果 `DEER_FLOW_CONFIG_PATH` 指向的 `config.yaml` 不存在，则自动生成
- 如果仓库根目录的 `.env` 不存在，则基于 `.env.example` 自动生成
- 如果 `frontend/.env` 不存在，则基于 `frontend/.env.example` 自动生成
- 按需在 `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 创建 `extensions_config.json`
- 在 `DEER_FLOW_HOME/cli-config/` 下创建默认的 CLI 配置目录
- 如果缺失，则把 `~/.claude/.credentials.json` 复制到 `$DEER_FLOW_HOME/cli-config/.claude/.credentials.json`
- 如果缺失，则把 `~/.codex/auth.json` 复制到 `$DEER_FLOW_HOME/cli-config/.codex/auth.json`
- 在 `DEER_FLOW_HOME` 下生成并持久化 `BETTER_AUTH_SECRET`

首次启动后，建议先停止服务，检查这些生成出来的文件，再决定是否进入日常使用阶段。

## 必要配置说明

### `config.yaml`

在本文档对应的场景里，只建议在“单个可信操作者 + 可信局域网”条件下使用 `LocalSandboxProvider`。

最小配置至少应满足：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
```

另外，在真正开始使用前，还需要在 `config.yaml` 里至少配置一个可用模型。

这里有两个非常容易踩的点：

- `models:` 必须是一个 YAML 列表，不能写成 `models:` 后面留空，也不能写成 `models: null`
- 如果你把 `database.backend` 改成 `postgres`，镜像里还必须安装 postgres 额外依赖，否则 gateway 启动时会报 `asyncpg is not installed`

如果你只是单机 NAS 部署，建议继续使用默认的 SQLite：

```yaml
database:
  backend: sqlite
  sqlite_dir: .deer-flow/data
```

如果你想通过 OpenRouter 接入免费模型，推荐最少先写成下面这样，再把 `model` 改成你在 OpenRouter 控制台当前可用的 `:free` 模型 ID：

```yaml
models:
  - name: openrouter-free
    display_name: OpenRouter Free
    use: langchain_openai:ChatOpenAI
    model: your-provider/your-model:free
    api_key: $OPENROUTER_API_KEY
    base_url: https://openrouter.ai/api/v1
    request_timeout: 600.0
    max_retries: 2
    max_tokens: 8192
    temperature: 0.7
```

说明：

- `OPENROUTER_API_KEY` 建议写在仓库根目录 `.env`
- 如果你当前只是想先把 NAS 跑起来，不要同时折腾 `postgres`
- 如果你确实需要 `postgres`，构建前先导出 `UV_EXTRAS=postgres`

### 根目录 `.env`

生产 compose 会把仓库根目录的 `.env` 注入 `gateway` 容器。你应该在这里填写模型提供商密钥和可选的 tracing 配置，例如：

```bash
OPENAI_API_KEY=your-openai-api-key
OPENROUTER_API_KEY=your-openrouter-api-key
TAVILY_API_KEY=your-tavily-api-key
```

如果你需要通过局域网 IP、NAS 主机名，或 ZeroTier IP 访问 DeerFlow，也建议把前端认证相关地址一起写在这里：

```bash
BETTER_AUTH_URL=http://10.81.172.129:2026
DEER_FLOW_TRUSTED_ORIGINS=http://10.81.172.129:2026,http://192.168.1.20:2026,http://nas.lan:2026
```

说明：

- `BETTER_AUTH_URL` 建议写成你最常用、最稳定的访问入口
- `DEER_FLOW_TRUSTED_ORIGINS` 需要包含所有你实际会在浏览器里打开的来源地址
- 如果你既会在局域网里访问，也会通过 ZeroTier 访问，就把这两类地址都写进去
- 新版 `deploy.sh` 在你没手动设置时会自动提供 `http://localhost:2026` 和 `http://127.0.0.1:2026` 的默认值，但 NAS/ZeroTier 场景仍然建议显式配置

另外也强烈建议在 `.env` 中显式设置固定的 JWT 签名密钥，避免重启后登录态全部失效：

```bash
AUTH_JWT_SECRET=请替换为一段随机长字符串
```

可以用下面的命令生成：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### `frontend/.env`

生产 compose 也会把 `frontend/.env` 注入前端容器。即使你只使用自动生成的默认内容，也建议保留这个文件。

## 仅局域网访问的建议

本文档假设 DeerFlow 只由单个可信操作者在可信局域网内使用。

- 只把 DeerFlow 端口开放给你的本地网络
- 不要把服务直接暴露到公网
- 不要把这套配置当成团队共享服务来使用
- 优先使用 NAS 防火墙或路由器规则，把访问限制在你的可信设备范围内
- 如果未来需要更大范围的访问，请优先参考上游安全与部署建议，而不是先去复制一份自定义 NAS compose 文件
- 如果你需要多用户或更强隔离能力，请改用更完整的 sandbox 配置方案，而不是继续使用 `LocalSandboxProvider`

## ZeroTier 访问补充

如果你使用 ZeroTier 从外部设备访问同一台 NAS，最关键的是浏览器访问地址必须和前端认证配置保持一致。

推荐做法：

1. 在仓库根目录 `.env` 中设置：

```bash
BETTER_AUTH_URL=http://10.81.172.129:2026
DEER_FLOW_TRUSTED_ORIGINS=http://10.81.172.129:2026,http://192.168.1.20:2026,http://nas.lan:2026
```

2. 重新启动部署：

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
./scripts/deploy.sh start
```

如果你修改了镜像或脚本，也可以重新执行完整的：

```bash
./scripts/deploy.sh
```

如果访问 `http://ZeroTier-IP:2026/workspace` 时看到类似 `trustedOrigins Required` 的报错，通常就是这里没有把 ZeroTier 的访问地址写进 `DEER_FLOW_TRUSTED_ORIGINS`。

如果你已经拉取了包含前端代理修复的新版本，但日志里仍然出现：

```text
Failed to proxy http://127.0.0.1:8001/...
```

不要只执行 `./scripts/deploy.sh start`。前端的内部网关地址会参与镜像构建，应该完整重建：

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
./scripts/deploy.sh down
./scripts/deploy.sh
```

原因是旧版前端镜像可能已经把 `127.0.0.1:8001` 固化进构建产物；新版本会在生产镜像里使用容器内可访问的 `http://gateway:8001`。

## 启动与停止

一步启动：

```bash
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
./scripts/deploy.sh
```

先构建、后启动：

```bash
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
./scripts/deploy.sh build
./scripts/deploy.sh start
```

停止：

```bash
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
./scripts/deploy.sh down
```

如果你更想继续使用仓库根目录里的配置文件，可以不导出上面的两个可选覆盖变量，这样 `deploy.sh` 会继续使用 `repo/config.yaml` 和 `repo/extensions_config.json`。

`./scripts/deploy.sh down` 只负责停止和移除容器，不会在一个全新的 checkout 目录里额外生成 `config.yaml`、`.env`、`frontend/.env` 或 CLI 运行目录。

## 关于 CLI 配置目录挂载

生产部署里包含了 Claude Code 和 Codex 认证目录的 bind mount，而且官方 compose 路径会把这些挂载稳定放到 `DEER_FLOW_HOME` 下的固定位置。

- `deploy.sh` 默认把 `DEER_FLOW_CLAUDE_CONFIG_DIR` 设为 `$DEER_FLOW_HOME/cli-config/.claude`
- `deploy.sh` 默认把 `DEER_FLOW_CODEX_CONFIG_DIR` 设为 `$DEER_FLOW_HOME/cli-config/.codex`

如果你不手动覆盖这两个变量，这些目录会自动落在 `DEER_FLOW_HOME` 下，并和其他运行时数据一样持久保存。

兼容行为如下：

- 如果启动时上面两个默认凭据文件还不存在，`deploy.sh` 只会复制这两个宿主机认证文件：
  - `~/.claude/.credentials.json`
  - `~/.codex/auth.json`
- 这样可以保持 `docker/docker-compose.yaml` 仍然使用官方 `DEER_FLOW_HOME` 挂载路径，而不是回退成直接绑定 `HOME`
- 如果你自己覆盖了 `DEER_FLOW_CLAUDE_CONFIG_DIR` 或 `DEER_FLOW_CODEX_CONFIG_DIR`，`deploy.sh` 不会再自动帮你复制宿主机凭据
- 如果之后需要刷新凭据，可以在这些运行目录里重新登录对应 CLI，或者手动把更新后的认证文件复制到默认或自定义目录中

## 升级路径

为了尽量跟上游保持一致，升级时建议继续沿用同一套官方生产路径，并保留已有运行时文件。

1. 保持 `DEER_FLOW_HOME` 不变
2. 保持你的配置路径选择不变：
   - 如果你使用仓库根目录默认值，就保留 `repo/config.yaml` 和 `repo/extensions_config.json`
   - 如果你使用持久化覆盖路径，就保持 `DEER_FLOW_CONFIG_PATH` 和 `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 继续指向同一批文件
3. 升级过程中保留以下文件：
   - `config.yaml`
   - `.env`
   - `frontend/.env`
   - `DEER_FLOW_HOME` 下已有的全部运行时数据
4. 更新 Git 仓库
5. 重新执行官方部署脚本

示例：

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
git pull --ff-only
./scripts/deploy.sh build
./scripts/deploy.sh start
```

因为你的持久化配置和运行时数据都保存在容器之外，重新构建镜像不会清掉已有部署状态。

如果你是为了拿到这次 NAS/ZeroTier 相关修复，升级后建议顺手确认：

```bash
git log -1 --oneline
```

然后执行完整重建，而不是只做 `start`。

## 日志与排障方式

在 NAS 上，最稳妥的生产排障方式是优先看容器日志：

```bash
docker logs --tail=120 deer-flow-frontend
docker logs --tail=120 deer-flow-gateway
docker logs --tail=120 deer-flow-nginx
```

不建议一上来就直接执行：

```bash
docker compose -p deer-flow -f docker/docker-compose.yaml logs
```

原因是生产 compose 依赖 `deploy.sh` 注入多个环境变量；如果你当前 shell 里没有先导出同一批变量，Compose 在解析阶段就可能报：

- `DEER_FLOW_CLAUDE_CONFIG_DIR must be set`
- `DEER_FLOW_CODEX_CONFIG_DIR must be set`
- `DEER_FLOW_DOCKER_SOCKET` 为空

如果你确实要直接用 `docker compose ... logs`，请先重新导出与部署时相同的环境变量；否则直接用 `docker logs` 更省事。

## 常见报错与处理

### 1. `/workspace` 或 `/setup` 打开时报 `trustedOrigins Required`

症状：

```text
Error: [
  {
    "path": ["trustedOrigins"],
    "message": "Required"
  }
]
```

处理：

- 在根目录 `.env` 中补齐 `BETTER_AUTH_URL`
- 在根目录 `.env` 中补齐 `DEER_FLOW_TRUSTED_ORIGINS`
- 把所有真实访问入口都写进去，包括局域网 IP、NAS 主机名、ZeroTier IP
- 修改后重新部署

### 2. 前端报 `ECONNREFUSED 127.0.0.1:8001` 或 `ECONNREFUSED gateway:8001`

症状：

```text
Failed to proxy http://127.0.0.1:8001/api/v1/auth/setup-status
Error: connect ECONNREFUSED 127.0.0.1:8001
```

或：

```text
Failed to proxy http://gateway:8001/api/v1/auth/setup-status
Error: connect ECONNREFUSED 172.x.x.x:8001
```

处理顺序：

1. 先看 `docker logs --tail=120 deer-flow-gateway`，确认 gateway 是否真的已经启动成功
2. 如果 gateway 正常，但前端还在访问旧地址，执行 `./scripts/deploy.sh down && ./scripts/deploy.sh` 做完整重建
3. 不要只执行 `./scripts/deploy.sh start`

### 3. gateway 启动时报 `models Input should be a valid list`

症状：

```text
1 validation error for AppConfig
models
  Input should be a valid list
```

处理：

- 打开 `config.yaml`
- 确认 `models:` 下面至少有一个模型条目
- 不要把 `models:` 留空或写成 `null`
- 可以先用上文的 OpenRouter 示例或任一官方示例模型启动

### 4. gateway 启动时报 `postgres but asyncpg is not installed`

症状：

```text
ImportError: database.backend is set to 'postgres' but asyncpg is not installed
```

处理二选一：

- 单机 NAS：把 `config.yaml` 改回 `database.backend: sqlite`
- 需要 Postgres：构建前导出 `UV_EXTRAS=postgres`，然后完整重建镜像

示例：

```bash
cd /volume1/docker/deer-flow/repo
export DEER_FLOW_HOME=/volume1/docker/deer-flow/data/deer-flow-home
export DEER_FLOW_CONFIG_PATH=$DEER_FLOW_HOME/config.yaml
export DEER_FLOW_EXTENSIONS_CONFIG_PATH=$DEER_FLOW_HOME/extensions_config.json
export UV_EXTRAS=postgres
./scripts/deploy.sh down
./scripts/deploy.sh
```

### 5. 登录后很快又掉线，或容器重启后必须重新登录

常见原因：

- `.env` 里没有固定的 `AUTH_JWT_SECRET`

处理：

- 在根目录 `.env` 中设置固定的 `AUTH_JWT_SECRET`
- 重新部署后再登录一次

### 6. 线程时间显示成“约 8 小时前”等明显不准确的相对时间

这通常不是 NAS 时区没配好，而是旧版前端对“无时区时间字符串”的解析有误。

处理：

- 升级到包含时间解析修复的新版本
- 完整重建前端镜像
- 刷新页面后再观察历史线程时间

### 7. Telegram 日志持续报 `Conflict: terminated by other getUpdates request`

症状：

```text
telegram.error.Conflict: Conflict: terminated by other getUpdates request
```

含义：

- 同一个 `TELEGRAM_BOT_TOKEN` 正在被多个实例同时轮询
- 这通常不是 DeerFlow 核心前后端链路故障，而是 Telegram Bot 使用冲突

处理：

- 如果你不需要 Telegram，就在 `config.yaml` 里禁用 `channels.telegram`
- 如果你需要 Telegram，确保只有一个 DeerFlow 实例或一个外部 bot 在使用这个 token
- 旧版本里如果 `gateway` 运行了多个 worker，也可能在同一个 DeerFlow 容器内部重复启动 Telegram polling；升级到包含 channel 单实例锁的新版本后，再完整重建镜像
- 如果 token 已经在聊天记录、截图或日志里暴露，立即去 BotFather 轮换 token，再更新 `.env` 或 `config.yaml`

### 8. Telegram / Feishu / Slack 收到消息后，gateway 日志报 `POST /api/threads/.../runs/wait 401 Unauthorized`

症状：

```text
POST /api/threads/<thread_id>/runs/wait HTTP/1.1" 401 Unauthorized
{"detail":{"code":"not_authenticated","message":"Authentication required"}}
```

含义：

- 这通常不是 bot token 错误，也不是用户登录态失效
- 旧实现里 IM channel 到 gateway 的“内部认证 token”是按 worker 进程随机生成的
- 当 `gateway` 开了多个 worker 时，channel service 在 A worker 里发出的内部请求，可能被 B worker 接住，于是被误判成未登录

处理：

- 升级到包含“共享内部认证 token”修复的新版本
- 完整重建 `gateway` 镜像并重启容器
- 如果你显式管理环境变量，也可以额外固定 `DEER_FLOW_INTERNAL_AUTH_TOKEN`
- 重启后再次观察日志，正常情况下不应再出现这类 `/runs/wait 401`

## 排查清单

- 如果 DeerFlow 自动生成了新的 `config.yaml`，请在正式使用前编辑它，并确认它仍然指向 `LocalSandboxProvider`
- 如果你只导出了 `DEER_FLOW_HOME`，要记得 `config.yaml` 和 `extensions_config.json` 依然默认在仓库根目录
- 如果你移动了仓库 checkout 目录，请保持 `DEER_FLOW_HOME` 不变，避免运行时数据分散到多个位置
- 如果 NAS shell 会忘记已导出的变量，建议把 `DEER_FLOW_HOME` 以及你用到的配置路径覆盖变量写入 shell profile 或 NAS 任务调度器
- 如果你需要自定义行为，优先使用 `deploy.sh` 已支持的环境变量覆盖，而不是去复制一份 `docker/docker-compose.yaml`
