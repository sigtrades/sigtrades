# SunnyQuant 合作兑换码（partner_campaign）

## 后台

- Kind：`partner_campaign`（模板，不可直接兑换）
- 赠送活动 `sunnyquant_pro_gift`：套餐 `pro`（SQ 后台赠送/试用）
- 付费活动 `sunnyquant_pro_paid`：套餐 `pro`（SQ Stripe/Paddle）
- **会员到期日以发码时传入的 `period_end` 为准**，与 SQ 会员到期严格对齐（不再用模板固定 1/30 天）
- Seed 会创建模板；生产环境请在 Admin「活动/兑换码」确认 **启用** 后再对外发码

## 内部发码

`POST /internal/partner/mint-code` + `X-Internal-Secret`

```json
{
  "campaign_key": "sunnyquant_pro_gift",
  "external_ref": "sq_membership:<uuid>:<period_end>",
  "partner": "sunnyquant",
  "period_end": "2026-08-30T00:00:00+00:00"
}
```

| 字段 | 说明 |
|------|------|
| `campaign_key` | 活动模板 key |
| `external_ref` | 幂等键；建议含 SQ membership id 与 period_end，续期变更到期日时用新 ref |
| `period_end` | **必填**，ISO8601；兑换后用户 `UserMembership.period_end` 严格等于此值 |
| `partner` | 合作方标识，默认 `sunnyquant` |

返回：`code`、`redeem_url`、`plan_code`、`membership_days`（展示用剩余天数）、`period_end`、`ends_at`（码本身过期时间=同一到期日）。

## 用户兑换

- API：`POST /config/promotions/redeem` `{ "code": "..." }`（需登录）
- Web：`/redeem?code=`（未登录先登录再自动兑换）
- 若码上带有 `membership_period_end`，发放时写入该绝对到期日；已过期则拒绝兑换

详见 SunnyQuant `docs/SIGTRADES_PARTNER_GIFT.md`。
