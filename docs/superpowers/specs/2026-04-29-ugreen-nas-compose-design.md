# 绿联云 NAS Docker Compose 部署适配设计

**日期**：2026-04-29
**分支**：当前工作区
**状态**：设计已确认，待用户 review 后进入实现计划
**适用场景**：`x86_64/Intel` 绿联云 NAS、局域网访问、`sandbox.use: deerflow.sandbox.local:LocalSandboxProvider`

---

## 1. 目标

基于仓库现有的 [`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml) 和 [`scripts/deploy.sh`](../../../scripts/deploy.sh) 提供一套对绿联云 NAS 更友好的生产部署方案，同时把“便于持续跟进官方更新”作为核心约束。

这次设计要同时满足三件事：

1. NAS 用户尽量按官方生产入口就能启动 DeerFlow，而不是维护第二套部署体系。
2. 适配内容尽量是通用增强，不把代码改成“只服务 NAS”的分支。
3. 后续跟进官方时，主要通过 `git pull` + 重建镜像完成升级，减少手工比对和合并冲突。

## 2. 当前状态与问题

### 2.1 已有基础

- 仓库已经提供生产 Compose 文件：[`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml)
- 仓库已经提供生产部署脚本：[`scripts/deploy.sh`](../../../scripts/deploy.sh)
- 默认 `config.example.yaml` 已经把 sandbox 配置为 `LocalSandboxProvider`，与本次 NAS 场景一致

这意味着我们不需要新建一套 `docker-compose.nas.yaml`，而是应该在现有入口上做最小适配。

### 2.2 对 NAS 场景不够友好的点

#### 问题 A：生产部署脚本不会自动补齐全部必需 env 文件

[`scripts/deploy.sh`](../../../scripts/deploy.sh) 当前会自动补齐：

- `config.yaml`
- `extensions_config.json`

但不会自动补齐：

- 项目根目录 `.env`
- [`frontend/.env`](../../../frontend/.env.example) 对应的运行时文件

而 [`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml) 中：

- `gateway` 使用 `env_file: ../.env`
- `frontend` 使用 `env_file: ../frontend/.env`

在 NAS 上如果用户直接按生产入口运行，很容易因为这两个文件不存在导致启动失败或启动体验不连贯。

#### 问题 B：Compose 对宿主机 `HOME` 下 CLI 配置目录有强依赖

[`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml) 的 `gateway` 当前默认绑定：

- `${HOME}/.claude`
- `${HOME}/.codex`

这对普通 Linux 开发机很自然，但在 NAS 的 Docker Compose / GUI 环境中不够稳妥，原因包括：

1. `HOME` 不一定按预期存在或可控。
2. 许多 NAS 用户并不会使用 Claude Code 或 Codex ACP。
3. 这些目录不存在时，用户需要额外理解它们的作用，徒增部署心智负担。

#### 问题 C：官方文档对 NAS 生产部署缺少聚焦说明

当前 README 里的 Docker 说明更偏通用 Linux 主机，没有专门说明：

- NAS 上推荐使用 `local sandbox`
- 只做局域网访问时的最小暴露端口方案
- 持久化目录应该放哪里
- 升级时哪些文件应该保留、哪些只需要重建

## 3. 设计原则

### 3.1 单一生产入口

继续以 [`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml) 作为唯一生产 Compose 文件，不新增 NAS 专用 Compose 文件。

### 3.2 适配做成通用增强

任何代码改动都优先服务“所有生产 Docker 用户”的健壮性，而不是只为绿联云 NAS 打补丁。

### 3.3 配置外置、行为保守

NAS 场景相关差异优先通过：

- 默认值
- 环境变量
- 文档约束

来处理，避免改动服务拓扑、镜像内容或运行逻辑。

### 3.4 优先降低后续升级成本

用户未来升级官方版本时，最好只需要：

1. 更新代码
2. 保留原有配置和数据目录
3. 重新构建并启动容器

而不是长期维护一套私有化部署分支。

## 4. 候选方案

| 方案 | 描述 | 是否推荐 |
|---|---|---|
| A | 只补 NAS 文档，不改代码 | 不推荐 |
| B | 新增 `docker-compose.nas.yaml` | 不推荐 |
| C | 保留官方生产入口，只做最小通用增强并补 NAS 文档 | 推荐 |

### 4.1 方案 A：只写文档

优点：

- 改动最少
- 不会碰部署代码

缺点：

- `.env` 和 `frontend/.env` 的缺失仍然会卡用户
- `HOME` 相关挂载问题仍然存在
- 用户每次部署都要自己记住额外步骤

### 4.2 方案 B：新增 NAS 专用 Compose

优点：

- 看起来最“贴合 NAS”

缺点：

- 形成第二套生产入口
- 未来需要持续同步官方 Compose 变化
- 与“方便长期跟官方更新”目标冲突

### 4.3 方案 C：最小通用增强 + NAS 指南

优点：

- 不分叉生产入口
- 提升现有生产部署健壮性
- 对上游变化更友好

缺点：

- 需要对现有部署脚本和 Compose 做少量改动

**结论**：采用方案 C。

## 5. 最终设计

### 5.1 部署拓扑

保留现有生产三服务结构：

- `nginx`
- `frontend`
- `gateway`

在本次目标场景下：

- 使用 `LocalSandboxProvider`
- 不启动 `provisioner`
- 只暴露一个局域网访问端口，默认仍为 `2026`

这意味着 NAS 用户仍然遵循官方生产路径，只是配置和文档更适配。

### 5.2 `deploy.sh` 自动补齐运行时文件

增强 [`scripts/deploy.sh`](../../../scripts/deploy.sh)，让生产部署前的文件准备逻辑覆盖以下四类文件：

- `config.yaml`
- `extensions_config.json`
- `.env`
- `frontend/.env`

行为要求：

1. 若文件不存在，则从示例文件自动生成：
   - `config.example.yaml -> config.yaml`
   - `.env.example -> .env`
   - `frontend/.env.example -> frontend/.env`
2. 若示例文件不存在，则保持当前报错或降级策略。
3. 若文件已存在，则绝不覆盖用户内容。

这样做的结果是：

- 用户可以直接走官方生产部署入口
- “首次部署缺文件”的问题在脚本层一次性兜住
- 这项增强同样适用于普通 Linux 生产环境

### 5.3 `gateway` 中 CLI 配置目录挂载改成可选、可配置

调整 [`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml) 中 `gateway` 的 `.claude` / `.codex` 挂载方式。

目标不是删除该能力，而是让它变成“对普通部署默认无负担，对需要的人显式启用”。

推荐行为：

1. 引入两个新的宿主机路径变量，例如：
   - `DEER_FLOW_CLAUDE_CONFIG_DIR`
   - `DEER_FLOW_CODEX_CONFIG_DIR`
2. 默认值落到 DeerFlow 数据目录下的占位目录，而不是 `${HOME}`。
3. `deploy.sh` 在启动前确保这些默认目录存在。

这样带来的效果：

- NAS 用户即使没有 Claude/Codex 本地配置，也能顺利启动
- 有高级需求的用户仍可通过环境变量覆盖到真实目录
- Compose 文件不再依赖 NAS 的 `HOME` 语义

### 5.4 绿联云 NAS 部署文档

新增一份中文文档，聚焦“如何基于官方生产 Compose 在绿联云 NAS 上部署”。

文档应覆盖：

1. 前提条件
   - `x86_64/Intel`
   - Docker / Docker Compose 可用
   - 局域网访问，不需要公网暴露
2. 推荐目录规划
   - 代码目录
   - `DEER_FLOW_HOME` 数据目录
   - 可选的 CLI 配置目录
3. 首次部署步骤
   - 获取代码
   - 生成/检查 `config.yaml`
   - 配置 `.env`
   - 启动命令
4. `config.yaml` 中推荐使用 `LocalSandboxProvider`
5. 局域网访问地址说明
6. 常见问题排查
   - 缺失环境文件
   - 模型 API key 未配置
   - 端口冲突
   - NAS 内存不足或构建耗时过长
7. 官方更新跟进建议

### 5.5 官方更新跟进策略

文档和设计里要明确推荐以下升级路径：

1. 不修改主 Compose 拓扑和服务定义。
2. 尽量只维护以下本地状态：
   - `config.yaml`
   - `.env`
   - `frontend/.env`
   - `DEER_FLOW_HOME`
3. 若有自定义宿主机挂载路径，通过环境变量或外部 `.env` 控制，而不是直接改 Compose 主体。
4. 升级时优先执行：
   - 拉取最新官方代码
   - 检查 `config.example.yaml` 是否新增必要字段
   - 重新构建镜像并启动
5. 若官方后续继续调整 `docker/docker-compose.yaml` 或 `scripts/deploy.sh`，本次改动应尽量保持局部、易合并。

## 6. 组件与数据流

### 6.1 首次启动流程

1. 用户在 NAS 上准备代码目录与数据目录
2. 运行生产部署入口
3. `deploy.sh` 检查并自动补齐缺失的配置文件
4. `deploy.sh` 检查并创建默认的 CLI 配置占位目录
5. `docker compose` 构建并启动 `frontend`、`gateway`、`nginx`
6. 用户通过 `http://NAS_IP:2026` 在局域网访问

### 6.2 升级流程

1. 停止旧容器
2. 更新官方仓库代码
3. 保留已有 `config.yaml`、`.env`、`frontend/.env` 与 `DEER_FLOW_HOME`
4. 重新构建镜像并启动
5. 如官方配置模板有新增字段，再手动补齐本地配置

## 7. 错误处理与边界

### 7.1 配置文件不存在

由 `deploy.sh` 负责自动生成，并明确输出提示说明哪些文件是从示例模板补齐的。

### 7.2 API key 未配置

容器可以启动，但运行模型能力会失败。文档中应明确把这类报错归因到 `.env` 或 `config.yaml` 的模型配置，而不是 Docker 本身。

### 7.3 CLI 配置目录不存在

不再视为部署阻塞错误。默认占位目录存在即可，只有用户明确启用相关 ACP/CLI 场景时才需要填入真实凭据目录。

### 7.4 NAS 资源不足

文档里应提示：

- 首次构建时间会比普通服务器更长
- 如果内存偏小，镜像构建和前端构建容易变慢或失败
- 生产使用建议尽量减少并发重任务

## 8. 测试与验证

实现阶段至少覆盖以下验证：

1. `deploy.sh` 在缺失 `.env` 和 `frontend/.env` 时能自动补齐
2. `deploy.sh` 不会覆盖已有配置文件
3. `docker/docker-compose.yaml` 在未设置 `HOME` 依赖时仍可被正确解析
4. 默认 CLI 配置占位目录存在时，`gateway` 可以正常启动
5. 在 `LocalSandboxProvider` 模式下，生产部署不会错误要求 Docker socket 或 `provisioner`
6. 文档步骤能完整对应实际命令与配置项

## 9. 实施范围

本次实现只包括：

- 小范围增强 [`scripts/deploy.sh`](../../../scripts/deploy.sh)
- 小范围增强 [`docker/docker-compose.yaml`](../../../docker/docker-compose.yaml)
- 新增绿联云 NAS 部署文档

本次不包括：

- 新增 NAS 专用 Compose 文件
- 修改服务拓扑
- 引入公网反向代理方案
- 为 ARM NAS 增加专门适配
- 调整 sandbox 运行机制

## 10. 风险与缓解

### 风险 1：可配置挂载目录的默认值设计不当

如果默认值仍然依赖复杂环境变量，NAS 兼容性改善会很有限。

缓解：

- 默认值尽量绑定到 `DEER_FLOW_HOME` 可控子目录
- 在 `deploy.sh` 中显式创建相关目录

### 风险 2：部署脚本增强与已有使用者预期不一致

有些用户可能不希望部署脚本自动生成额外文件。

缓解：

- 仅在缺失时生成
- 输出清晰提示
- 不覆盖已有文件

### 风险 3：文档与真实实现漂移

如果文档步骤与脚本实际行为不一致，NAS 用户仍然会被卡住。

缓解：

- 实现后按文档步骤做一轮实际验证
- 文档直接引用真实文件名、真实环境变量名与真实端口

## 11. 后续计划入口

在用户确认本 spec 后，下一步进入实现计划阶段，重点拆解为：

1. `deploy.sh` 的文件补齐与目录准备逻辑
2. `docker-compose.yaml` 的 CLI 配置目录参数化
3. NAS 文档编写与验证
