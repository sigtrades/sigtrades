# IBKR Web API（First Party / 高级）

云端券商标识：`ibkr_web`。与本地 `ibkr`（TWS + Relay Agent）并存。

## 适用场景

- 个人在 [IBKR OAuth Self-Service](https://ndcdyn.interactivebrokers.com/sso/Login?action=OAUTH&RL=1&ip2loc=US) 生成密钥后，粘贴到控制台。
- 由 `cloud-executor` 调用 `api.ibkr.com`，无需本机 TWS。

## 限制

- 多腿组合暂不支持（请用 TWS Agent）。
- 同一 IB 用户名同时只能有一个经纪会话：使用 Web API 时请关闭 TWS/网页交易会话。
- 第三方「一键授权」需 IBKR Compliance，本路径是 First Party 自用凭证。

## 凭证字段

| secrets | 说明 |
|---|---|
| consumer_key | Self-Service Consumer Key |
| access_token | Access Token |
| access_token_secret | Access Token Secret（加密形态） |
| signature_key_pem | 签名私钥 PEM |
| encryption_key_pem | 加密私钥 PEM |
| dh_prime | DH modulus（hex 或 dhparam.pem） |

`config.env`：`paper` / `live`（标识）；`config.account_id` / 凭证行 `account_id`：IB 账户号。

## 一键生成

控制台「新增账号 → 盈透 Web API」内点 **一键生成密钥**：

- `POST /broker-credentials/ibkr-web/generate-keys`（需登录，**不落库**）
- 自动填入签名/加密私钥与 `dhparam.pem`
- 浏览器下载 `public_signature.pem`、`public_encryption.pem`、`dhparam.pem` 供上传 IBKR
- Consumer Key / Access Token 仍须在 IBKR Self-Service 完成后再粘贴

## 执行链路

```text
Signal → signal-router (deployment_for("ibkr_web") == cloud)
      → cloud-executor → IbkrWebBrokerAdapter → ExecutionCore
```
