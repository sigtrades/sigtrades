# sigtrades

全栈信号跟单平台：云端 + 桌面 Relay Agent + SaaS。外部信号进入 → 解析 → 裁决 → 自动下单或通知。

详见 [PRD.md](./PRD.md)。

## Monorepo 结构

```
sigtrades/
├── packages/
│   ├── core/         # sigtrades_core: 信号模型 / 券商适配器 / 执行状态机 / 信号源接口
│   └── protocol/     # sigtrades_protocol: relay WS 消息 schema + 内部契约
├── services/
│   ├── api-server/      # 认证 / 会员 / Stripe / 后台 / 信号配置（FastAPI）
│   ├── signal-router/   # 校验 + 动作裁决 + 路由分叉
│   ├── relay-gateway/   # Agent 反向 WS hub
│   ├── cloud-executor/  # 云端券商执行（老虎 / 长桥 / 嘉信 / Alpaca）
│   └── ingest/          # 插件式信号连接器宿主（Discord / Telegram / TradingView webhook）
├── clients/
│   └── relay-agent/     # 桌面 headless Agent（Mac/Windows，无 UI）
├── web/                 # 营销首页 + 应用（React + Vite + i18n）
├── web-admin/           # 后台管理（用户/计划/信号源/Agent/执行审计）
├── docker-compose.yml   # 云端服务编排
├── Caddyfile            # 可选统一入口（with-proxy profile）
├── data/geoip/          # GeoIP 数据库（make download-geoip）
├── scripts/             # 运维脚本
└── docs/                # 架构 / 协议文档
```

## 功能概览

- **SaaS**：JWT / Google OAuth / 邮箱验证 / 找回密码 / 会员 entitlements / Stripe 订阅 / Resend 邮件
- **信号**：Webhook HMAC · Discord Bot Gateway · Telegram Bot · TradingView JSON · AI/正则解析 · 路由/风控/幂等
- **执行**：老虎/长桥/嘉信/Alpaca 云端 · IBKR/富途 Relay Agent · 止损止盈 · 账户级幂等
- **通知**：站内 + 邮件 + Webhook + FCM（Dashboard 可注册 device token）
- **邮件**：Resend 发信 + 入站 Webhook（`POST /mail/webhook/received`）+ web-admin 收件箱
- **GeoIP**：登录/注册记录 IP/国家；后台用户分布；`make download-geoip` 下载 MaxMind mmdb
- **Agent**：`--check-update` / `SIGTRADES_AUTO_UPDATE` 自动检查并下载新版本
- **前端**：营销页 · Dashboard（Telegram / FCM / TradingView）· web-admin（用户/收件箱/计划/信号源）· 中英 i18n

## 券商部署切分

| 券商 | 连接 | 执行位置 |
|------|------|----------|
| 老虎 | REST (tigeropen) | 云端 cloud-executor |
| 长桥 | OpenAPI (longbridge) | 云端 cloud-executor |
| 嘉信 | Trader API (OAuth 2.0) | 云端 cloud-executor |
| Alpaca | Trading API (API Key) | 云端 cloud-executor |
| 富途 | 本地 OpenD :11111 | 桌面 Relay Agent |
| IBKR | 本地 TWS :7497/:7496 | 桌面 Relay Agent |

## 本地开发

### Docker（推荐：一键拉起云端全链路）

编排文件在仓库根目录 **`docker-compose.yml`**。

```bash
# 首次：复制环境变量并填写 FERNET_KEY
cp .env.example .env

# 方式一：Makefile
make docker-up          # 构建并启动全部云端服务
make docker-ps          # 查看容器状态
make docker-logs        # 跟踪 api-server 日志

# 方式二：直接 docker compose（仓库根目录）
docker compose up -d --build
```

**服务端口**（`docker compose up -d --build` 后可直接访问）

| 服务 | 地址 |
|------|------|
| 用户前端 web | http://localhost:5173 |
| 管理后台 web-admin | http://localhost:5174 |
| api-server | http://localhost:8080 |
| relay-gateway | ws://localhost:8081/agent/ws |
| ingest (webhook) | http://localhost:8082/ingest/wh/{token} |
| redis | 容器内网（api-server 通过 `redis://redis:6379` 访问） |

前端容器内 nginx 将 `/api/*` 代理到 `api-server`，无需再单独跑 `npm run dev`。

可选 Caddy 单端口入口（仅用户前端 + API）：`docker compose --profile with-proxy up -d`（需本地已有 `web/dist` 或改用 web 容器）。Caddy 同时代理 `/mail/*`（Resend 入站 Webhook）。

GeoIP 数据库（可选，用于后台国家统计）：

```bash
make download-geoip MAXMIND_LICENSE_KEY=your_maxmind_key
docker compose up -d api-server   # 挂载 data/geoip → /app/data/geoip
```

### 本地 Python / 前端开发

若已用 Docker 跑全栈（含 web / web-admin 容器），可跳过本节。需要热更新时再本地起 Vite：

```bash
# 安装共享核心（可编辑）
pip install -e packages/core
pip install -e packages/protocol

# 前端热更新（API 走 Docker 8080）
cd web && npm install && npm run dev   # http://localhost:5173
cd web-admin && npm install && npm run dev  # http://localhost:5174
```

### 一键验证

```bash
docker compose up -d --build
make verify          # 检查各服务 health + demo 登录
make test            # 后端单元测试（18 项）
```

浏览器手动验证：

1. 打开 http://localhost:5173 → 用 `demo@sigtrades.app` / `demo1234` 登录
2. Dashboard → 生成 **Agent Token**（富途/IBKR 本机执行需要）
3. 打开 http://localhost:5174 → 填入 `.env` 里的 `ADMIN_TOKEN` → 查看用户列表

### Relay Agent（本机程序，不进 Docker）

Agent 负责连接本机 **IBKR / 富途 OpenD**，通过 WebSocket 连到 `relay-gateway`（Docker 映射 **8081**）。自带 **pywebview 桌面设置窗口**（内置 React UI，本地静态资源，非远端加载）。

**开发模式：**

```bash
cd clients/relay-agent/ui && npm install && npm run build
cd .. && pip install -e ../../packages/core -e ../../packages/protocol -e .
pip install pywebview ib_async futu-api   # 按需
sigtrades-agent          # 默认打开桌面窗口
sigtrades-agent --no-window   # 纯后台
```

**打包 + 提供下载（Mac / Windows）：**

```bash
make build-agent     # 产出到 data/agent-releases/
# 脚本会打印 AGENT_DOWNLOAD_URL / AGENT_SHA256，写入 .env 后：
docker compose up -d api-server
```

- 版本 API：`GET http://localhost:8080/public/agent-version`
- 安装包下载：`http://localhost:8080/releases/sigtrades-agent-macos-v0.1.x.dmg`（拖入「应用程序」）或 Windows zip
- Agent 自动更新：设置 `SIGTRADES_VERSION_CHECK_URL=http://localhost:8080/public/agent-version`

生产环境可将 zip 上传到 GitHub Releases / OSS，把 `AGENT_DOWNLOAD_URL` 改成公网地址。CI 见 `.github/workflows/build-agent.yml`（打 tag `agent-v*` 触发）。

### Demo 账号（SEED_DEMO=true 时自动创建）

- 邮箱：`demo@sigtrades.app` / 密码：`demo1234`
- 登录后创建 Agent token：`POST /agent-tokens`（需 Bearer JWT）
- 或查看 api-server 启动日志中的 demo agent/webhook token

### 信号链路

```
Webhook/Discord/Telegram/TradingView → ingest → signal-router → api-server(resolve-routing)
                              ├→ cloud-executor (老虎/长桥/嘉信/Alpaca)
                              └→ relay-gateway → relay-agent (IBKR/富途)
```

## 设计原则

- 统一标准接口：信号源 `BaseSignalSource`、券商 `BaseBrokerAdapter`、Agent relay 协议；下游对来源/券商无感知。
- 凭证分级：老虎/长桥/Alpaca 密钥与嘉信 OAuth 授权加密存云；富途/IBKR 凭证仅本机。
- 凭证分级：老虎/长桥/Alpaca 密钥与嘉信 OAuth 授权加密存云；富途/IBKR 凭证仅本机。
- 交易数据云端落库；全链路 `(source_id, signal_id)` 幂等。
