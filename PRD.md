# sigtrades 产品需求文档（PRD）

全栈信号跟单平台：云端 + 桌面 Relay Agent + SaaS。外部信号进入 → 解析 → 裁决 → 自动下单或通知。

> 本文档为产品/架构需求说明。落地代码位于本 monorepo；sigx、sunny-quant 仅作参考，sigtrades 不出现任何 sunny-quant 专有命名/字段/协议。

## 1. 产品定位
- 接收来自多种外部来源的交易信号（外部 WS 信号服务、Discord、TradingView、Telegram 等），统一解析为内部信号模型，按用户配置自动下单或通知。
- 核心差异化：**支持本地网关类券商**（富途 OpenD、IBKR TWS/Gateway），通过桌面 Relay Agent 中转执行——这是纯云 OAuth 方案（如 SignalStack）覆盖不到的能力。
- 老虎证券（REST）与长桥 OpenAPI 走云端执行，用户零安装；富途/IBKR 走本地 Agent。

## 2. 关键设计原则
- **统一标准接口**：信号源 → `BaseSignalSource`，券商 → `BaseBrokerAdapter`，Agent → relay 协议。外部系统专有协议/字段封闭在各自 adapter/connector 内，下游对来源无感知。
- **凭证分级**：老虎/长桥密钥应用层加密（Fernet）存云、运行时解密；富途/IBKR 凭证仅留用户本机，绝不上云。
- **交易数据云端落库**：凭证留本机，但下单金额/买卖/成交必须回传云端记录（审计/风控/计费/合规）。
- **幂等**：全链路 `(source_id, signal_id[, account_id])` 去重，断线重连不重复下单。

## 3. 系统组成
| 模块 | 路径 | 职责 |
|------|------|------|
| 共享核心 | `packages/core` (`sigtrades_core`) | 信号模型、券商适配器、执行状态机、信号源接口 |
| 协议 | `packages/protocol` | relay WS 消息 schema、内部 push-gate 契约 |
| api-server | `services/api-server` | 认证/会员/Stripe/后台/信号配置/内部校验 |
| signal-router | `services/signal-router` | 校验 entitlements/风控 → 动作裁决 → 路由分叉 |
| relay-gateway | `services/relay-gateway` | Agent 反向 WS hub、连接路由、离线处理 |
| cloud-executor | `services/cloud-executor` | 老虎/长桥云端执行（共用 execution_core） |
| ingest | `services/ingest` | 插件式信号连接器宿主（先 Discord） |
| relay-agent | `clients/relay-agent` | 桌面无 UI Agent（Mac/Windows），本地执行富途/IBKR |
| web | `web` | 营销首页 + 应用（auth/会员/dashboard） |
| web-admin | `web-admin` | 后台管理 |
| docker-compose | 根目录 | 云端服务 Docker 编排（Caddy / GeoIP 等辅助资源同目录） |

## 4. 信号源（多源可插拔，两类 ownership）
- **平台共享源**：一条信号广播给多订阅者（外部 WS 信号服务、策展 Discord 源）。
- **用户私有源**：一条信号只属于该用户（Discord 频道跟随、个人 webhook）。
- **三种接入形态**：WS 订阅、Webhook 推送（`/ingest/wh/{token}` + HMAC）、REST 轮询。
- **新增源 = 加一个 connector/adapter + 注册配置**，不动下游。

## 5. 快速接入 + 解析/动作配置（核心）
- 每用户唯一签名 webhook URL，贴进 TradingView/任意平台即用。
- **解析规则 `user_parse_rules`**（per 频道/源）：AI 解析（默认）/ 正则模板 / 结构化 JSON；带样例预览测试工具。
- **动作 `user_route_rules`**（per 源/信号类型）：自动交易 / 仅通知 / 两者；可按信号类型分流。
- **下单类型策略 `order_type_policy`**：`LMT_then_MKT`（带可靠价）/ `MKT_only`（Discord/文本解析默认，对应 `limit_order_attempts=0`）。

## 6. Discord（插件式连接器，合规优先）
- ingest 为连接器宿主；Discord 为首个 connector，Telegram/TradingView 后续同接口接入。
- **路径 1 策展共享源**（推荐）：服主授权官方 bot → 源目录 → 用户 app 内一键订阅。
- **路径 2 自助（重心）**：用户自有服务器 OAuth bot 邀请 + 公告频道 Channel Following。
- **明确不做 selfbot**（违反 Discord ToS）。
- AI 解析自然语言为结构化信号，通常无可靠限价 → 默认市价单。

## 7. 桌面 Relay Agent（Mac + Windows，无 PySide6）
- 反向长连接 `wss://relay/agent/ws`，认证 `user_token + device_id + capabilities`，心跳/重连。
- **执行职责全在本地**：网关类券商的下单/订单查询/重试/撤单重下/幂等都在 Agent；云端不参与本地订单查询重试。
- 线程模型：IBKR 专属事件循环线程承载 `ib_async`；富途 worker 线程；WS 主循环用 `run_coroutine_threadsafe` 桥接。
- 仅回传有意义的状态变更（`execution_report` 含完整成交明细）；凭证仅本机。
- 打包 PyInstaller：Mac `.app`+codesign+notarize；Windows `.exe`+代码签名；CI 分平台 runner 构建。

## 8. 券商配置（字段级）
- **老虎（云端）**：`private_key`(PKCS8 内容,加密存云)、`license`(默认 TBNZ)、`env`(test/production)、`test/production.{tiger_id,account}`、`sandbox`。
- **长桥（云端）**：`app_key`、`app_secret`、`access_token`（加密存云）、`env`(sandbox/live)。
- **IBKR（本地）**：`host`、`port`(TWS 7497/7496)、`client_id`、`account`、`readonly`。
- **富途（本地）**：`host`、`port`(11111)、`trd_env`(模拟/真实)。
- **纸上交易**首期支持。

## 9. SaaS（api-server）
- 认证：JWT access+refresh、bcrypt、Google OAuth、邮箱验证/找回。
- 会员：`membership_plans`/`user_memberships` + feature 实体化 entitlements + `has_feature()` 门控。
- Stripe：consent → checkout-session → webhook 同步 → Customer Portal / 降级调度。
- 会员权益映射：信号源数量、可连券商数、AI 解析开关、每日跟单上限、多设备 Agent。
- 内部 push-gate API（`X-Internal-Secret`）供 signal-router 校验。

## 10. 强平台能力
- 风控：止损/止盈、最大单笔/总仓位、每日下单数与亏损上限、交易时段。
- 多账户/多券商扇出（幂等键加 `account_id`）。
- 全局急停 kill switch。
- 执行审计全链路（源→解析→裁决→下单→回执）。
- 资产类别：首期 **期权 + 股票**；期货/加密后续。

## 11. 多语言（i18n，全栈）
- 首期中英，`users.language` 统一遵循；web/web-admin i18next；api-server 多语言邮件 + Accept-Language；通知按用户语言；Agent 本地化；AI 解析兼容多语言喊单。

## 12. 部署
- 云端服务全部容器化（Docker + docker-compose），含 PostgreSQL + Redis。
- 前端静态托管；Nginx/Caddy 终结 TLS 并支持 WS upgrade。
- 桌面 Agent 不进 Docker（PyInstaller 打包）。

## 13. 离线/缺口
- Agent 离线：超时即弃 + 通知，默认不补单；`agent_offline`/`agent_ok` 状态。
- 待补齐：全链路幂等落地、真正状态回传链、执行逻辑单一来源、AES 解密路径统一、Alembic 迁移。
