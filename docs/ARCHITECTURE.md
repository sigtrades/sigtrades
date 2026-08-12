# sigtrades 架构概览

## 组件

| 组件 | 职责 |
|------|------|
| **ingest** | 插件式信号连接器（Webhook / Discord）；归一化 Signal |
| **signal-router** | 权益校验、动作裁决、路由到 cloud-executor 或 relay-gateway |
| **api-server** | SaaS：认证、会员、Stripe、用户配置、内部 push-gate |
| **relay-gateway** | Agent 反向 WebSocket hub |
| **cloud-executor** | 老虎、长桥、嘉信、Alpaca 云端执行 |
| **relay-agent** | 本地 IBKR/富途执行（execution_core） |

## 数据流

```
外部源 → ingest → signal-router → api-server(resolve-routing)
                    ├→ cloud-executor (tiger/longbridge/schwab/alpaca)
                    └→ relay-gateway → relay-agent (ibkr/futu)
```

## 设计原则

- 统一接口：`BaseSignalSource` / `BaseBrokerAdapter` / relay 协议
- 凭证：老虎/长桥/Alpaca 密钥与嘉信 OAuth 授权 Fernet 加密存云；IBKR/富途仅本机
- 幂等：`(source_id, signal_id[, account_id])`
- 交易回执云端落库

详见 [PRD.md](../PRD.md)、[RELAY_PROTOCOL.md](./RELAY_PROTOCOL.md)。
