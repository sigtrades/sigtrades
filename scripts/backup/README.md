# SigTrades 关键表备份（香港 → mac-mini）

只备份用户 / 会员 / 券商绑定 / webhook token 等（`data-only`），不含 `execution_records`。

流程：香港按表 dump → gzip → scp 到 mac-mini → 删临时文件 → 留 3 份。

## 谁执行

- **只在 mac-mini 装 cron**；香港部署不会自动跑。
- 配置：`config/pg_backup.json`
- 失败告警：Resend → `backup@sigtrades.com`

## 手动跑

```bash
cd /Users/yangjun/work/sigtrades
python3 scripts/backup/backup_critical.py
```

## 定时（北京时间 08:05，与 SQ 错开）

mac-mini LaunchAgent：

```bash
cp scripts/backup/com.sigtrades.pg-backup.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sigtrades.pg-backup.plist
```

系统时区需为 `Asia/Shanghai`。

## 恢复

灌入已有 schema 的库；勿直接覆盖生产。
