export const PLAN_FEATURE_OPTIONS = [
  { key: "auto_trade", label: "自动交易" },
  { key: "ai_parse", label: "AI 解析" },
  { key: "discord_multi_channel", label: "Discord 多频道" },
  { key: "multi_agent", label: "多 Agent" },
] as const;

export const PLAN_LIMIT_KEYS = [
  { key: "max_signal_sources", label: "信号源上限" },
  { key: "max_brokers", label: "券商账号上限" },
  { key: "max_discord_channels", label: "Discord 频道上限" },
] as const;
