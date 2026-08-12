export function formatBrokers(brokers: unknown): string {
  if (brokers == null) return "—";
  if (Array.isArray(brokers)) return brokers.map(String).filter(Boolean).join(", ") || "—";
  if (typeof brokers === "object") {
    return Object.entries(brokers as Record<string, unknown>)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(" · ");
  }
  return String(brokers);
}

export function formatKvValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((v) => formatKvValue(v)).join(", ");
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return "—";
    if (entries.length <= 4) {
      return entries.map(([k, v]) => `${k}: ${formatKvValue(v)}`).join(" · ");
    }
    return `${entries.length} 项配置`;
  }
  return String(value);
}

const SIGNAL_FIELDS: { key: string; label: string }[] = [
  { key: "symbol", label: "标的" },
  { key: "action", label: "动作" },
  { key: "side", label: "方向" },
  { key: "quantity", label: "数量" },
  { key: "price", label: "价格" },
  { key: "order_type", label: "订单类型" },
  { key: "source", label: "来源" },
  { key: "strategy", label: "策略" },
  { key: "expiry", label: "到期" },
  { key: "strike", label: "行权价" },
];

export function signalSummaryRows(signal: Record<string, unknown>): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  for (const { key, label } of SIGNAL_FIELDS) {
    const v = signal[key];
    if (v !== undefined && v !== null && v !== "") {
      rows.push({ label, value: String(v) });
    }
  }
  return rows;
}
