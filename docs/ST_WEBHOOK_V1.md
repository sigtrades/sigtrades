# SigTrades Webhook 推送标准（st_webhook_v1）

面向用户可粘贴的 Webhook JSON：字段对齐内部 `Signal`，ingest 透传进 signal-router。

## 接入

1. Dashboard → 信号源 / 流水线 → 新建 **Webhook**，复制  
   `POST https://<ingest-host>/ingest/wh/{token}`
2. 将下方 JSON 作为 HTTP body（`Content-Type: application/json`）POST 到该 URL  
   或在 UI「信号 JSON」生成器中填表后复制
3. 可选 HMAC：`X-Signature`（sha256 hex）

## 识别

ingest（`services/ingest/app/connectors/webhook.py`）在 SunnyQuant 之后优先识别：

- `contract_version: "st_webhook_v1"`，或
- 同时带有 `signal_id` + `action` 的结构化 body

`contract_version` 会写入 `signal.metadata.contract_version`，不进入下单字段。

## 股票示例

```json
{
  "contract_version": "st_webhook_v1",
  "signal_id": "st-20260729-001",
  "action": "BUY",
  "symbol": "AAPL",
  "quantity": 10,
  "order_type": "MKT",
  "asset_class": "STOCK"
}
```

## 期权示例（1–4 腿）

每腿 `symbol` 使用 OCC 风格（与后端 `format_broker_option_symbol` 一致）：  
`UNDERLYING YYMMDD{C|P}########`（行权价 ×1000，8 位）。

```json
{
  "contract_version": "st_webhook_v1",
  "signal_id": "st-20260729-002",
  "action": "SELL",
  "symbol": "SPX",
  "quantity": 1,
  "order_type": "MKT",
  "asset_class": "OPTIONS",
  "signal_subtype": "OPEN",
  "legs": [
    {
      "symbol": "SPX 240119P04500000",
      "action": "SELL",
      "quantity": 1,
      "strike": 4500,
      "option_type": "PUT"
    }
  ],
  "metadata": {
    "underlying": "SPX",
    "expiry": "2024-01-19"
  }
}
```

多腿时顶层 `action` 建议为 `组合`；不同到期日写在各腿 OCC `symbol` 内，`metadata.expiry` 取第一腿即可。

## 字段摘要

| 字段 | 规则 |
|------|------|
| `contract_version` | 固定 `st_webhook_v1` |
| `signal_id` | 幂等键组成部分；生成器默认 `st-{短id}` |
| `action` | 股票 BUY/SELL；多腿可用 `组合` |
| `symbol` | 股票=标的；期权=underlying |
| `quantity` | 股票股数 / 组合乘数 |
| `asset_class` | `STOCK` \| `OPTIONS` |
| `order_type` | `MKT`（默认）或 `LMT`（配合 `limit_price`） |
| `legs` | 仅期权，1–4 条 |
| `signal_subtype` | 可选 `OPEN` / `CLOSE` |

## 与其它格式

| 来源 | 识别 | 说明 |
|------|------|------|
| st_webhook_v1 | `contract_version` / 结构化透传 | 本标准 |
| TradingView 简写 | `ticker` 或 `symbol`（无完整 signal_id 契约） | `{ "ticker","action","quantity" }` |
| SunnyQuant | `sq_webhook_v2` | 见 [SUNNYQUANT_WEBHOOK.md](./SUNNYQUANT_WEBHOOK.md) |

三者共用同一 Webhook URL；按 payload 分流，勿把 Webhook 产品能力改名为单一合作方。

## 参考

- 内部信封：[SIGNAL_PROTOCOL.md](./SIGNAL_PROTOCOL.md)
- 前端生成：`web/src/lib/stWebhookV1.ts`、`WebhookSignalJsonModal`
