# notify 模块

通知能力内嵌于 `notify_service.py`，由 signal-router / relay-gateway / ingest 经 `POST /internal/notify` 触发。

## 渠道

| 渠道 | 配置 | 说明 |
|------|------|------|
| 邮件 | `RESEND_API_KEY` + `RESEND_FROM_EMAIL`（推荐）或 `SMTP_*` | 按 `users.language` 选模板 |
| Webhook | `NOTIFY_PUSH_WEBHOOK` | 自定义推送网关 |
| FCM v1 | `FCM_PROJECT_ID` + `FCM_CREDENTIALS_JSON`（或 `FCM_CREDENTIALS_PATH`）+ `POST /push-token` | Firebase HTTP v1 API；无效 token 自动清理 |

Web 端一键注册：`FIREBASE_WEB_API_KEY` / `FIREBASE_VAPID_KEY` 等 → `GET /public/firebase-config`

## 事件类型

`signal` · `execution` · `agent_offline` · `agent_ok` · `parse_failed` · `risk_blocked`
