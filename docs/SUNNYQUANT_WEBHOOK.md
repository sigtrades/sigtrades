# SunnyQuant Webhook 接入（sq_webhook_v2）

SigTrades 可直接接收 SunnyQuant「API 推送」POST 的 JSON，无需手写解析规则。

## 配置步骤

1. **SigTrades**：Dashboard → 信号源 → 新建 **Webhook**，复制 ingest URL  
   `POST https://<ingest-host>/ingest/wh/{token}`

2. **SunnyQuant**：Dashboard → API 推送 → 填入上述 URL，开启结构提醒 + 对应策略

3. **SigTrades 执行管道**：将该 Webhook 源绑定到路由规则（建议 **仅通知** 或 **确认后下单**；v2 不含预组单腿）

## 身份与执行账号（不看邮箱）

- **只认 URL 后缀 token**：`/ingest/wh/{token}` → 查 `webhook_ingest_tokens` → 得到 `source_id` + `owner_user_id`
- 用该用户在该 `source_id` 下的 **路由规则 + 券商绑定** 执行
- **不**用 SunnyQuant / SigTrades 两边邮箱做关联；payload 里的 `subscriber.user_id` 仅写入 `metadata.sunnyquant`
- 券商匹配以 **`account_id` 为准**；`account_label` 仅展示/兜底

## 自动识别

ingest 在 `services/ingest/app/connectors/sunnyquant.py` 识别：

- `contract_version`: `sq_webhook_v2`（推荐）或 legacy `sq_webhook_v1`
- 或 `source`: `sunnyquant.gex_structure_reminder`

请求头（SunnyQuant 侧）：`X-SunnyQuant-Contract: sq_webhook_v2`  
幂等：`Idempotency-Key: {user_id}:{signal_id}`（SigTrades 侧仍按 `(source_id, signal_id)` 去重）

## v2 契约（当前，与 SunnyQuant 前台示例一致）

与邮件 / Bark / 站内信号卡 **同文**：`title` + `content` + `disclaimer`。  
`structure.references` 为中性观察参考位（非下单腿）。**一律不含** `order` / `execution` / `quantity`。

示例（完整字段见 SunnyQuant `front/src/constants/apiPushWebhookExample.ts`）：

```json
{
  "contract_version": "sq_webhook_v2",
  "event": "structure_signal",
  "signal_id": "GEX_20260619_093100_pcs_basic",
  "timestamp": 1739811660,
  "strategy": "SQ-TGT",
  "strategy_family": "vertical_spread",
  "audience": "pcs_basic",
  "signal_subtype": "ENTRY",
  "asset_class": "SPX_OPTIONS",
  "direction": "down",
  "spx_price": 6123.45,
  "title": "PCS 信号观察开始 · …",
  "content": "**PCS 信号观察开始 · …**",
  "disclaimer": "本提醒由系统根据 GEX 结构数据自动生成…",
  "structure": {
    "exit_reason": null,
    "parent_signal_id": null,
    "spx_price": 6123.45,
    "reference_width": 20,
    "references": [{ "option_type": "P", "inner": 6050, "outer": 6030 }]
  },
  "delivery": { "tier": "external", "delay_sec": 0, "deliver_after_ts": 1739811660 },
  "subscriber": { "user_id": "…" },
  "source": "sunnyquant.gex_structure_reminder"
}
```

## v2 内容型 → SigTrades Signal 映射

| SunnyQuant | SigTrades `signal` |
|------------|-------------------|
| `signal_id` | `signal_id` |
| `timestamp` | `timestamp` |
| `title` | `metadata.sunnyquant.title`（通知邮件摘要首行展示） |
| `strategy` | `strategy` |
| `signal_subtype` | `signal_subtype`（ENTRY→OPEN，EXIT→CLOSE，REF/TAKE_PROFIT 保留） |
| `asset_class` | `asset_class` |
| — | `signal_category` = `ALERT` |
| — | `auto_trade_enabled` = `false` |
| — | `quantity` = `0`，`legs` = `null` |
| 信封全文 | `metadata.sunnyquant`（含 `title`/`content`/`disclaimer`/`structure`/`delivery` 等） |

> v2 为 **结构观察提醒**，不是预组交易指令。`auto_trade_enabled=false` 会在路由层强制降级为 **仅通知**（即使管道配了自动下单 / 确认后下单也不会发券商），防止 `default_quantity` 把 `quantity=0` 补成真实数量后误下单。

## 路由建议

| SunnyQuant `audience` | 建议 `user_route_rules` |
|-----------------------|-------------------------|
| `pcs_basic` / `pcs_short` | PCS 管道 |
| `ccs_basic` / `ccs_short` | CCS 管道 |
| `ic` | 铁鹰管道 |

可按 `metadata.sunnyquant.strategy`（SQ-xx）或 `strategy_family` 再细分。

## 兼容

| 契约 | 说明 |
|------|------|
| **sq_webhook_v2 + order** | 旧内部测试格式，仍映射为 `TRADE` + `legs` |
| **sq_webhook_v1** | `metadata` 壳，映射为 `ALERT`，`legacy_v1=true` |

## 安全

- Webhook 源可配置 HMAC secret（`X-Signature`）
- SunnyQuant 请求头：`X-SunnyQuant-Contract: sq_webhook_v2`

## 参考

- SunnyQuant 契约：`docs/API_PUSH_WEBHOOK_v2.md`（SunnyQuant 仓库）
- 前台可复制 JSON：`sunny-quant/front/src/constants/apiPushWebhookExample.ts`
- 内部协议：`docs/SIGNAL_PROTOCOL.md`
