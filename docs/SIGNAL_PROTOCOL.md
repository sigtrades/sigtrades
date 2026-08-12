# 信号协议（内部）

## InboundSignal 信封

signal-router 接收的统一入站格式：

```json
{
  "source_id": "wh-abc123",
  "signal_id": "wh-uuid",
  "ownership": "user_private",
  "owner_user_id": "uuid",
  "signal": { "action": "BUY", "symbol": "AAPL", "quantity": 10, "order_type": "MKT" }
}
```

## 幂等键

`(source_id, signal_id)`；多账户扇出时扩展 `(source_id, signal_id, account_id)`。

## 解析

- **structured**：JSON 字段映射
- **regex**：用户正则 + capture groups
- **ai**：LLM（无 key 时降级启发式）
- Discord/自由文本默认 `order_type_policy=MKT_only`

## Webhook

- URL：`POST /ingest/wh/{token}`
- 可选 HMAC：`X-Signature: sha256 hex`

### SigTrades 标准（st_webhook_v1）

用户可粘贴的推送 JSON（股票 / 最多 4 腿期权），对齐内部 `Signal` 透传。详见 [ST_WEBHOOK_V1.md](./ST_WEBHOOK_V1.md)。

### SunnyQuant（sq_webhook_v2）

SunnyQuant API 推送可直接 POST 至同一 Webhook URL。ingest 识别 `contract_version: sq_webhook_v2`（`structure_signal` 内容型，与邮件/Bark 同文）并映射为 standard Signal；`metadata.sunnyquant` 保留全文。详见 [SUNNYQUANT_WEBHOOK.md](./SUNNYQUANT_WEBHOOK.md)。

### TradingView 简写

Alert Message 常见 `{ "ticker","action","quantity" }`，无 `contract_version` 时走 TV 兼容分支。

## 动作（user_route_rules）

- `auto_trade` / `notify_only` / `both`
- 按 `signal_subtype` 分流（可选）
