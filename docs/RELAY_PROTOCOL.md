# Relay 协议（云端 ↔ 桌面 Agent）

反向长连接：Agent 主动连云端 `relay-gateway` 的 `wss://.../agent/ws`。所有消息为 JSON，含顶层 `type`。

实现：`packages/protocol/sigtrades_protocol/relay.py`。

## 连接与认证
1. Agent 连接 WS，首帧发送 `agent_register`（`user_token` + `device_id` + `capabilities`）。
2. relay-gateway 校验 `user_token`（向 api-server 验证），通过后登记 `user_id → 连接`。
3. 同一 `device_id` 重复登录：踢旧连接。

## 消息

### 上行（Agent → 云）
| type | 说明 |
|------|------|
| `agent_register` | 上线注册：账号 token、设备、能力、平台、版本 |
| `agent_heartbeat` | 心跳保活 |
| `agent_status` | 各券商网关连通性（在线/离线展示） |
| `execution_report` | 执行回执，含完整成交明细（落库审计/风控/计费） |

### 下行（云 → Agent）
| type | 说明 |
|------|------|
| `execute_signal` | 整条已裁决信号 + 券商 + 账户 + 下单类型策略 |
| `cancel_signal` | 撤销某信号关联订单 |
| `pause_agent` | 全局急停（停止所有自动交易） |
| `ack` | 通用确认 |

## 幂等
- `execute_signal` 带 `signal_id` + `source_id`。
- Agent 本地按 `(source_id, signal_id[, account_id])` 去重；已有终态返回缓存结果，在途则恢复监控而非重新下单。

## 离线
- Agent 离线时云端无法下发 → signal-router 记 `DISCARDED_AGENT_OFFLINE` 并通知用户（默认不补单）。
- 重新上线发 `agent_register` + `agent_status`，云端清除离线状态。

## 回执时机
- 仅回传有意义的状态变更（提交/成交/部分/撤销/失败/跳过），不回传每次轮询噪音。
- 终态与成交金额必须回传。
