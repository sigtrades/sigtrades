# 嘉信（Charles Schwab）Trader API 接入

## 接入方式

嘉信使用 **Trader API + OAuth 2.0**，属于 sigtrades 云端券商，由
`cloud-executor` 执行，不经过 Relay Agent。

官方资料：

- [OAuth 认证](https://developer.schwab.com/user-guides/get-started/authenticate-with-oauth)
- [OAuth restart 与 refresh token](https://developer.schwab.com/user-guides/apis-and-apps/oauth-restart-vs-refresh-token)
- [Trader API 文档](https://developer.schwab.com/products/trader-api--individual/details/documentation/Retail%20Trader%20API%20Production)

首页使用的 Charles Schwab 标志仅用于标识受支持的第三方集成；Charles Schwab
商标归其权利人所有，不表示双方存在背书或合作关系。

## 准备凭证

1. 在 Schwab Developer Portal 创建启用了 Trader API 的应用（状态需 **Ready for Use**）。
2. 将 Portal **Callback URL** 设为与控制台「Callback URL」**完全一致**（不要尾斜杠）：
   - **推荐（自动回流）**：`http://127.0.0.1:5173/schwab/callback`（或你实际打开控制台的 origin + `/schwab/callback`）
   - **兜底（粘贴）**：`https://127.0.0.1`（嘉信社区常用；浏览器页打不开，需把地址栏整段 URL 粘回控制台）
3. 在 Web 控制台先保存 `Client ID` / `Client Secret`，Callback 与 Portal 保持一致。
4. 点「授权并连接」→ 打开官方授权链接  
   `https://api.schwabapi.com/v1/oauth/authorize?client_id=...&redirect_uri=...`。
5. 登录并授权：
   - 自动回流：浏览器回到 `/schwab/callback`，系统自动换票提交
   - 粘贴模式：地址栏出现 `https://127.0.0.1/?code=...` → **整段粘贴**（粘贴后会自动提交；授权码约 30 秒过期且一次性）
6. 系统写入 `refresh_token`、`hashValue`、Account Number。

若卡在 `login-one-step` 循环：核对 App 为 Ready for Use、Callback 完全一致；勿在授权 URL 附加无关长参数。  
若 `exchange_failed` 含 `authorization_code_expired`：重新点授权获取新 code，立刻提交。

敏感字段进入 `secrets_encrypted`，界面不返回明文。

## 执行链路

```text
Signal
  → signal-router (deployment_for("schwab") == "cloud")
  → cloud-executor
  → OAuth refresh
  → POST /trader/v1/accounts/{accountHash}/orders
  → GET /trader/v1/accounts/{accountHash}/orders/{orderId}
  → execution report
```

相关接口：

- Token：`POST https://api.schwabapi.com/v1/oauth/token`
- 账户映射：`GET /trader/v1/accounts/accountNumbers`
- 账户：`GET /trader/v1/accounts/{accountHash}`
- 下单：`POST /trader/v1/accounts/{accountHash}/orders`
- 查单：`GET /trader/v1/accounts/{accountHash}/orders/{orderId}`
- 撤单：`DELETE /trader/v1/accounts/{accountHash}/orders/{orderId}`

## 当前支持范围

- 美股股票：市价单、限价单
- 单腿美股期权：市价单、限价单
- DAY / GTC
- 订单状态查询、成交均价归一化、撤单
- Access Token 失效时自动使用 Refresh Token 刷新

暂不支持：

- 多腿组合期权
- OCO / TRIGGER 等复杂订单
- 成交后自动提交嘉信原生保护子单
- Refresh Token 自动重新授权

Refresh Token 失效后必须重新完成 OAuth 授权。未重新授权前，执行会明确失败，
不会降级为未认证请求或转发到其他券商。
