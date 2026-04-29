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

### 根目录 `.env`

生产 compose 会把仓库根目录的 `.env` 注入 `gateway` 容器。你应该在这里填写模型提供商密钥和可选的 tracing 配置，例如：

```bash
OPENAI_API_KEY=your-openai-api-key
TAVILY_API_KEY=your-tavily-api-key
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

## 排查清单

- 如果 DeerFlow 自动生成了新的 `config.yaml`，请在正式使用前编辑它，并确认它仍然指向 `LocalSandboxProvider`
- 如果你只导出了 `DEER_FLOW_HOME`，要记得 `config.yaml` 和 `extensions_config.json` 依然默认在仓库根目录
- 如果你移动了仓库 checkout 目录，请保持 `DEER_FLOW_HOME` 不变，避免运行时数据分散到多个位置
- 如果 NAS shell 会忘记已导出的变量，建议把 `DEER_FLOW_HOME` 以及你用到的配置路径覆盖变量写入 shell profile 或 NAS 任务调度器
- 如果你需要自定义行为，优先使用 `deploy.sh` 已支持的环境变量覆盖，而不是去复制一份 `docker/docker-compose.yaml`
