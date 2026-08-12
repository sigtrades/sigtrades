# Alpaca Trading API 接入

Alpaca 属于 sigtrades 云端券商，由 `cloud-executor` 直接调用 Trading API，
不经过 Relay Agent。

官方资料：

- [Getting Started](https://docs.alpaca.markets/us/docs/getting-started)
- [Authentication](https://docs.alpaca.markets/us/docs/authentication)
- [Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading)
- [Options Orders](https://docs.alpaca.markets/us/docs/options-orders)
- [Create an Order](https://docs.alpaca.markets/us/reference/postorder)

## 凭证与环境

在 Alpaca Dashboard 为对应环境创建 API Key：

- Paper：`https://paper-api.alpaca.markets`
- Live：`https://api.alpaca.markets`

Paper 与 Live 使用不同的 API Key。保存字段：

- `api_key`
- `api_secret`
- `env`：`paper` 或 `live`
- `account_id`：仅用于 sigtrades 界面识别

API Key 与 Secret 整体进入 `secrets_encrypted`，不会通过凭证查询接口返回明文。

## 执行链路

```text
Signal
  → signal-router (deployment_for("alpaca") == "cloud")
  → cloud-executor
  → GET /v2/account
  → POST /v2/orders
  → GET /v2/orders/{orderId}
  → execution report
```

## 当前支持

- 美股股票与单腿美股期权
- Market / Limit
- DAY / GTC
- Paper / Live
- 下单、查单、订单状态归一化与撤单
- Alpaca compact OCC 期权代码，例如 `AAPL260626C00297500`

暂不支持多腿期权、Bracket/OCO/OTO 与 Alpaca OAuth 用户授权。建议先用 Paper
环境完成端到端验证，再保存 Live 环境凭证。

首页使用的 Alpaca 标志来自其官方
[Newsroom Brand Assets](https://alpaca.markets/newsroom)，仅用于标识受支持的第三方集成；
Alpaca 商标归其权利人所有，不表示双方存在背书或合作关系。
